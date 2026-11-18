import argparse
import csv
import json
import sys
from functools import partial
from pathlib import Path

import cv2

from pipeline.leitura import ler_adiante
from training.datasets.openimages import NOMES
from training.datasets.yolo import (
    escrever_data_yaml,
    escrever_data_yaml_conjunto,
    guardar_exemplo,
)

SINAIS= (
    "object--traffic-sign--front",
    "object--traffic-sign--direction-front",
    "object--traffic-sign--information-parking",
    "object--traffic-sign--temporary-front",
)
POSTES= ("object--support--pole", "object--support--utility-pole")
LUZ= "object--street-light"
SEMAFORO= "object--traffic-light--"
LIXO= "object--trash-can"
DIVISOES= {"training": "train", "validation": "val"}
LADO_ANONIMIZAR= 2048
LADO_MINIMO_PX= 10
TOLERANCIA_LATERAL= 0.5
LICENCA= "CC BY-NC-SA 4.0"
ORIGEM_URL= "https://www.mapillary.com/dataset/vistas"


def _caixa(poligono: list[list[float]]) -> tuple[float, float, float, float]:
    xs= [p[0] for p in poligono]
    ys= [p[1] for p in poligono]
    return min(xs), min(ys), max(xs), max(ys)


def _com_poste(luz, postes):
    x0, y0, x1, y1= luz
    folga= (x1 - x0) * TOLERANCIA_LATERAL
    centro= (x0 + x1) / 2
    candidatos= [
        p
        for p in postes
        if p[2] >= x0 - folga and p[0] <= x1 + folga and p[3] > y1 and p[1] <= y1
    ]
    if not candidatos:
        return luz
    poste= min(candidatos, key=lambda p: abs((p[0] + p[2]) / 2 - centro))
    return min(x0, poste[0]), min(y0, poste[1]), max(x1, poste[2]), max(y1, poste[3])


def caixas_de(anotacao: dict) -> list[tuple[int, float, float, float, float]]:
    largura= anotacao["width"]
    altura= anotacao["height"]
    objetos= anotacao.get("objects", [])
    postes= [_caixa(o["polygon"]) for o in objetos if o["label"] in POSTES and o["polygon"]]
    caixas= []
    for objeto in objetos:
        rotulo= objeto["label"]
        if not objeto["polygon"]:
            continue
        if rotulo in SINAIS:
            nome= "outro"
            caixa= _caixa(objeto["polygon"])
        elif rotulo.startswith(SEMAFORO):
            nome= "semaforo"
            caixa= _caixa(objeto["polygon"])
        elif rotulo == LUZ:
            nome= "candeeiro"
            caixa= _com_poste(_caixa(objeto["polygon"]), postes)
        elif rotulo == LIXO:
            nome= "contentor"
            caixa= _caixa(objeto["polygon"])
        else:
            continue
        caixas.append((NOMES.index(nome), caixa[0] / largura, caixa[1] / altura, caixa[2] / largura, caixa[3] / altura))
    return caixas


def tamanho_suficiente(caixa: tuple[float, float, float, float, float], largura: int, altura: int, lado: int) -> bool:
    escala= min(1.0, lado / max(largura, altura))
    _, x0, y0, x1, y1= caixa
    return max((x1 - x0) * largura, (y1 - y0) * altura) * escala >= LADO_MINIMO_PX


def escolher(chaves: list[str], maximo: int | None) -> list[str]:
    ordenadas= sorted(chaves)
    if maximo is None or len(ordenadas) <= maximo:
        return ordenadas
    passo= len(ordenadas) / maximo
    return [ordenadas[int(i * passo)] for i in range(maximo)]


def _ler(origem: Path, divisao_vistas: str, chave: str):
    imagem= cv2.imread(str(origem / divisao_vistas / "images" / f"{chave}.jpg"))
    anotacao= json.loads((origem / divisao_vistas / "v2.0" / "polygons" / f"{chave}.json").read_text(encoding="utf-8"))
    return imagem, anotacao


def converter(
    origem: Path,
    saida: Path,
    anonimizador,
    lado: int,
    maximos: dict[str, int | None],
    registo,
    trabalhadores: int= 4,
) -> dict[str, int]:
    feitas= {}
    for divisao_vistas, divisao in DIVISOES.items():
        pasta_poligonos= origem / divisao_vistas / "v2.0" / "polygons"
        if not pasta_poligonos.is_dir():
            raise FileNotFoundError(f"Falta {pasta_poligonos}: é a pasta mtsd_v2_fully_annotated (Vistas v2.0)?")
        chaves= escolher([f.stem for f in pasta_poligonos.glob("*.json")], maximos.get(divisao))
        pendentes= [c for c in chaves if not (saida / "labels" / divisao / f"{c}.txt").exists()]
        feitas[divisao]= len(chaves) - len(pendentes)
        leitor= ler_adiante(partial(_ler, origem, divisao_vistas), pendentes, trabalhadores)
        for n, (chave, (imagem, anotacao)) in enumerate(leitor, 1):
            if imagem is None:
                print(f"Aviso: imagem ilegível {chave}", file=sys.stderr)
                continue
            largura= anotacao["width"]
            altura= anotacao["height"]
            caixas= [c for c in caixas_de(anotacao) if tamanho_suficiente(c, largura, altura, lado)]
            guardar_exemplo(saida, divisao, chave, imagem, caixas, anonimizador, lado, LADO_ANONIMIZAR)
            registo.writerow([chave, divisao, "Mapillary Vistas", LICENCA, ORIGEM_URL])
            feitas[divisao]+= 1
            if n % 200 == 0:
                print(f"[{divisao}] {n}/{len(pendentes)}", file=sys.stderr, flush=True)
    escrever_data_yaml(saida, NOMES)
    return feitas


def main(argv: list[str] | None= None) -> int:
    parser= argparse.ArgumentParser(prog="python -m training.datasets.vistas")
    parser.add_argument("--origem", required=True, help="pasta mtsd_v2_fully_annotated (Vistas v2.0)")
    parser.add_argument("--saida", default="data/datasets/vistas")
    parser.add_argument("--egoblur", default="models/egoblur")
    parser.add_argument("--lado", type=int, default=1280)
    parser.add_argument("--max-train", type=int, default=6000)
    parser.add_argument("--max-val", type=int, default=600)
    parser.add_argument("--trabalhadores", type=int, default=4)
    args= parser.parse_args(argv)
    from pipeline.anonymize.egoblur import Anonymizer

    saida= Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    nova= not (saida / "atribuicao.csv").exists()
    try:
        with (saida / "atribuicao.csv").open("a", newline="", encoding="utf-8") as ficheiro:
            registo= csv.writer(ficheiro)
            if nova:
                registo.writerow(["image_id", "divisao", "autor", "licenca", "url"])
            feitas= converter(
                Path(args.origem),
                saida,
                Anonymizer.from_dir(Path(args.egoblur)),
                args.lado,
                {"train": args.max_train, "val": args.max_val},
                registo,
                args.trabalhadores,
            )
    except FileNotFoundError as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    pastas= [p for p in (saida.parent / "openimages", saida) if (p / "data.yaml").exists()]
    conjunto= escrever_data_yaml_conjunto(saida.parent / "grandes.yaml", pastas, NOMES)
    print(f"Pronto: {feitas}. Treino com {conjunto}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
