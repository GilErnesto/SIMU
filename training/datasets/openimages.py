import argparse
import csv
import random
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import requests

from training.datasets.yolo import escrever_data_yaml, guardar_exemplo, ler_adiante

BASE= "https://storage.googleapis.com/openimages"
META= {
    "train_caixas": f"{BASE}/v6/oidv6-train-annotations-bbox.csv",
    "val_caixas": f"{BASE}/v5/validation-annotations-bbox.csv",
    "train_imagens": f"{BASE}/2018_04/train/train-images-boxable-with-rotation.csv",
    "val_imagens": f"{BASE}/2018_04/validation/validation-images-with-rotation.csv",
}
URL_IMAGEM= "https://open-images-dataset.s3.amazonaws.com/{pasta}/{id}.jpg"
CLASSES= {
    "/m/01mqdt": "outro",
    "/m/015qff": "semaforo",
    "/m/033rq4": "candeeiro",
    "/m/0bjyj5": "contentor",
}
NOMES= ["outro", "semaforo", "candeeiro", "contentor"]
SEMENTE= 0


def descarregar(url: str, destino: Path, saida=sys.stderr) -> Path:
    resposta= requests.get(url, stream=True, timeout=60)
    resposta.raise_for_status()
    tamanho= int(resposta.headers.get("content-length", 0))
    if destino.exists() and destino.stat().st_size == tamanho:
        resposta.close()
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial= destino.with_suffix(".parcial")
    with parcial.open("wb") as ficheiro:
        for bloco in resposta.iter_content(1 << 20):
            ficheiro.write(bloco)
    parcial.rename(destino)
    print(f"descarregado {destino.name}", file=saida, flush=True)
    return destino


def ler_caixas(caminho: Path) -> dict[str, list[tuple]]:
    por_imagem= defaultdict(list)
    excluidas= set()
    with caminho.open(newline="", encoding="utf-8") as ficheiro:
        for linha in csv.DictReader(ficheiro):
            classe= CLASSES.get(linha["LabelName"])
            if classe is None:
                continue
            if linha["IsGroupOf"] == "1" or linha["IsDepiction"] == "1":
                excluidas.add(linha["ImageID"])
                continue
            por_imagem[linha["ImageID"]].append(
                (classe, float(linha["XMin"]), float(linha["YMin"]), float(linha["XMax"]), float(linha["YMax"]))
            )
    return {k: v for k, v in por_imagem.items() if k not in excluidas}


def ler_info(caminho: Path, ids: set[str]) -> dict[str, dict]:
    info= {}
    with caminho.open(newline="", encoding="utf-8") as ficheiro:
        for linha in csv.DictReader(ficheiro):
            if linha["ImageID"] not in ids:
                continue
            if linha.get("Rotation", "") not in ("", "0", "0.0"):
                continue
            info[linha["ImageID"]]= {
                "autor": linha.get("Author", ""),
                "licenca": linha.get("License", ""),
                "url": linha.get("OriginalLandingURL") or linha.get("OriginalURL", ""),
            }
    return info


def escolher(caixas: dict[str, list[tuple]], maximo_por_classe: int, semente: int= SEMENTE) -> list[str]:
    ids= sorted(caixas)
    random.Random(semente).shuffle(ids)
    contagem= defaultdict(int)
    escolhidos= []
    for imagem_id in ids:
        presentes= {c[0] for c in caixas[imagem_id]}
        if all(contagem[c] >= maximo_por_classe for c in presentes):
            continue
        escolhidos.append(imagem_id)
        for c in presentes:
            contagem[c]+= 1
    return escolhidos


def _baixar_imagem(pasta_remota: str, imagem_id: str) -> np.ndarray | None:
    try:
        resposta= requests.get(URL_IMAGEM.format(pasta=pasta_remota, id=imagem_id), timeout=60)
    except requests.RequestException:
        return None
    if resposta.status_code != 200:
        return None
    return cv2.imdecode(np.frombuffer(resposta.content, np.uint8), cv2.IMREAD_COLOR)


def preparar_divisao(
    divisao: str,
    pasta_remota: str,
    caixas: dict[str, list[tuple]],
    info: dict[str, dict],
    saida: Path,
    anonimizador,
    lado: int,
    trabalhadores: int,
    registo,
) -> int:
    pendentes= [i for i in caixas if i in info and not (saida / "labels" / divisao / f"{i}.txt").exists()]
    feitas= 0
    leitor= ler_adiante(lambda i: _baixar_imagem(pasta_remota, i), pendentes, trabalhadores)
    for n, (imagem_id, imagem) in enumerate(leitor, 1):
        if imagem is None:
            continue
        caixas_norm= [(NOMES.index(c), x0, y0, x1, y1) for c, x0, y0, x1, y1 in caixas[imagem_id]]
        guardar_exemplo(saida, divisao, imagem_id, imagem, caixas_norm, anonimizador, lado)
        dados= info[imagem_id]
        registo.writerow([imagem_id, divisao, dados["autor"], dados["licenca"], dados["url"]])
        feitas+= 1
        if n % 200 == 0:
            print(f"[{divisao}] {n}/{len(pendentes)}", file=sys.stderr, flush=True)
    return feitas


def main(argv: list[str] | None= None) -> int:
    parser= argparse.ArgumentParser(prog="python -m training.datasets.openimages")
    parser.add_argument("--saida", default="data/datasets/openimages")
    parser.add_argument("--max-por-classe", type=int, default=3000)
    parser.add_argument("--max-val-por-classe", type=int, default=400)
    parser.add_argument("--egoblur", default="models/egoblur")
    parser.add_argument("--lado", type=int, default=1280, help="lado maior máximo das imagens gravadas")
    parser.add_argument("--trabalhadores", type=int, default=16)
    args= parser.parse_args(argv)
    from pipeline.anonymize.egoblur import Anonymizer

    saida= Path(args.saida)
    meta= saida / "meta"
    ficheiros= {nome: descarregar(url, meta / Path(url).name) for nome, url in META.items()}
    anonimizador= Anonymizer.from_dir(Path(args.egoblur))
    nova= not (saida / "atribuicao.csv").exists()
    with (saida / "atribuicao.csv").open("a", newline="", encoding="utf-8") as ficheiro:
        registo= csv.writer(ficheiro)
        if nova:
            registo.writerow(["image_id", "divisao", "autor", "licenca", "url"])
        for divisao, pasta_remota, chave, maximo in (
            ("val", "validation", "val", args.max_val_por_classe),
            ("train", "train", "train", args.max_por_classe),
        ):
            caixas= ler_caixas(ficheiros[f"{chave}_caixas"])
            escolhidos= escolher(caixas, maximo)
            info= ler_info(ficheiros[f"{chave}_imagens"], set(escolhidos))
            caixas= {i: caixas[i] for i in escolhidos}
            print(f"[{divisao}] {len(escolhidos)} imagens escolhidas, {len(info)} sem rotação", file=sys.stderr)
            feitas= preparar_divisao(
                divisao, pasta_remota, caixas, info, saida, anonimizador, args.lado, args.trabalhadores, registo
            )
            print(f"[{divisao}] {feitas} imagens gravadas", file=sys.stderr, flush=True)
    escrever_data_yaml(saida, NOMES)
    print(f"Pronto: {saida / 'data.yaml'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
