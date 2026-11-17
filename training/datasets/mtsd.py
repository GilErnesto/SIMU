import argparse
import json
import sys
from pathlib import Path

import cv2

from pipeline.rotulos_mapillary import classificar
from training.datasets.yolo import escrever_data_yaml, guardar_exemplo

NOMES= ["stop", "cedencia", "limite_velocidade", "proibicao", "perigo", "obrigacao", "informacao", "outro"]
DIVISOES= {"train": "train", "val": "val"}


def _partes(caixa: dict) -> list[dict]:
    atravessa= caixa.get("cross_boundary")
    if atravessa:
        return [atravessa["left"], atravessa["right"]]
    return [caixa]


def caixas_de(anotacao: dict) -> list[tuple[int, float, float, float, float]]:
    largura= anotacao["width"]
    altura= anotacao["height"]
    caixas= []
    for objeto in anotacao.get("objects", []):
        if objeto.get("properties", {}).get("dummy"):
            continue
        decisao= classificar(objeto["label"])
        if decisao is None or decisao[0] != "sinal" or decisao[1] not in NOMES:
            continue
        indice= NOMES.index(decisao[1])
        for parte in _partes(objeto["bbox"]):
            caixas.append(
                (
                    indice,
                    parte["xmin"] / largura,
                    parte["ymin"] / altura,
                    parte["xmax"] / largura,
                    parte["ymax"] / altura,
                )
            )
    return caixas


def converter(origem: Path, saida: Path, anonimizador, lado: int, limite: int | None= None) -> dict[str, int]:
    feitas= {}
    for divisao_mtsd, divisao in DIVISOES.items():
        lista= origem / "splits" / f"{divisao_mtsd}.txt"
        if not lista.exists():
            raise FileNotFoundError(f"Falta {lista}: é a pasta mtsd_v2_fully_annotated?")
        chaves= [c.strip() for c in lista.read_text(encoding="utf-8").splitlines() if c.strip()]
        feitas[divisao]= 0
        for n, chave in enumerate(chaves[:limite], 1):
            if (saida / "labels" / divisao / f"{chave}.txt").exists():
                feitas[divisao]+= 1
                continue
            anotacao_path= origem / "annotations" / f"{chave}.json"
            imagem= cv2.imread(str(origem / "images" / f"{chave}.jpg"))
            if imagem is None or not anotacao_path.exists():
                print(f"Aviso: falta a imagem ou a anotação de {chave}", file=sys.stderr)
                continue
            anotacao= json.loads(anotacao_path.read_text(encoding="utf-8"))
            guardar_exemplo(saida, divisao, chave, imagem, caixas_de(anotacao), anonimizador, lado)
            feitas[divisao]+= 1
            if n % 500 == 0:
                print(f"[{divisao}] {n}/{len(chaves)}", file=sys.stderr, flush=True)
    escrever_data_yaml(saida, NOMES)
    return feitas


def main(argv: list[str] | None= None) -> int:
    parser= argparse.ArgumentParser(prog="python -m training.datasets.mtsd")
    parser.add_argument("--origem", required=True, help="pasta mtsd_v2_fully_annotated, com as imagens extraídas")
    parser.add_argument("--saida", default="data/datasets/mtsd")
    parser.add_argument("--egoblur", default="models/egoblur")
    parser.add_argument("--lado", type=int, default=2048, help="lado maior máximo (os sinais são pequenos)")
    parser.add_argument("--limite", type=int, help="só as primeiras N imagens de cada divisão")
    args= parser.parse_args(argv)
    from pipeline.anonymize.egoblur import Anonymizer

    try:
        feitas= converter(
            Path(args.origem), Path(args.saida), Anonymizer.from_dir(Path(args.egoblur)), args.lado, args.limite
        )
    except FileNotFoundError as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    print(f"Pronto: {feitas} imagens em {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
