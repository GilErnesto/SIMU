"""Converts reviewed gold-set folders (see `pipeline.ouro`) into a YOLO dataset."""

import argparse
import hashlib
import json
import random
import shutil
from pathlib import Path

import cv2

from pipeline.detect.ladrilhos import LADO_LADRILHO, MINIMO_PARA_LADRILHAR, PASSO_LADRILHO, _inicios
from training.datasets.yolo import escrever_data_yaml, linhas_yolo

NOMES= ["outro", "semaforo", "candeeiro", "contentor"]
FRACAO_VALIDACAO= 0.15


def e_validacao(nome: str) -> bool:
    return int(hashlib.sha1(nome.encode()).hexdigest(), 16) % 100 < FRACAO_VALIDACAO * 100


FRACAO_DENTRO= 0.5


def ladrilhos(largura: int, altura: int, caixas: list[tuple[int, float, float, float, float]]):
    """Training tiles like the ones `detetar_com_ladrilhos` searches, with boxes in pixels.

    A box is kept, clipped to the tile, when at least half of it is inside.
    """
    for y in _inicios(altura, LADO_LADRILHO, PASSO_LADRILHO):
        for x in _inicios(largura, LADO_LADRILHO, PASSO_LADRILHO):
            lado_x, lado_y= min(LADO_LADRILHO, largura), min(LADO_LADRILHO, altura)
            dentro= []
            for indice, x0, y0, x1, y1 in caixas:
                a, b= max(x0, x), max(y0, y)
                c, d= min(x1, x + lado_x), min(y1, y + lado_y)
                if c <= a or d <= b or (c - a) * (d - b) < FRACAO_DENTRO * (x1 - x0) * (y1 - y0):
                    continue
                dentro.append((indice, (a - x) / lado_x, (b - y) / lado_y, (c - x) / lado_x, (d - y) / lado_y))
            yield x, y, lado_x, lado_y, dentro


def degradar_foto(rng: random.Random, foto):
    """A whole photo as a worse camera would take it: blurred, shaken, compressed, dark or low-res.

    Boxes do not move, so the labels stay valid.
    """
    import numpy as np

    from training.tipos_web import _desfocar

    escolha= rng.random()
    if escolha < 0.3:
        foto= cv2.GaussianBlur(foto, (0, 0), rng.uniform(1.0, 3.0))
    elif escolha < 0.55:
        foto= _desfocar(random.Random(rng.random()), foto)
    elif escolha < 0.75:
        altura, largura= foto.shape[:2]
        escala= rng.uniform(0.3, 0.6)
        pequena= cv2.resize(foto, (round(largura * escala), round(altura * escala)), interpolation=cv2.INTER_AREA)
        foto= cv2.resize(pequena, (largura, altura), interpolation=cv2.INTER_LINEAR)
    else:
        foto= np.clip(foto.astype(np.float32) * rng.uniform(0.3, 0.6), 0, 255).astype(np.uint8)
    _, codificada= cv2.imencode(".jpg", foto, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(8, 60)])
    return cv2.imdecode(codificada, cv2.IMREAD_COLOR)


def converter(
    pastas: list[Path],
    saida: Path,
    com_ladrilhos: bool= False,
    copias_degradadas: int= 0,
    so_treino: list[Path] | None= None,
) -> tuple[int, int]:
    """so_treino: folders (e.g. pseudo-labels) never used for validation, so early stopping
    is judged on human labels only."""
    so_treino= list(so_treino or [])
    if saida.exists():
        shutil.rmtree(saida)
    imagens= caixas= 0
    for pasta in [*pastas, *so_treino]:
        dados= json.loads((pasta / "ouro.json").read_text(encoding="utf-8"))
        for nome, tela in dados["telas"].items():
            if not tela["revista"]:
                continue
            largura, altura= tela["largura"], tela["altura"]
            itens= [
                (NOMES.index("semaforo" if c["classe"] == "semaforo" else "outro"),
                 c["caixa"][0] / largura, c["caixa"][1] / altura, c["caixa"][2] / largura, c["caixa"][3] / altura)
                for c in tela["caixas"]
                if c["estado"] in ("aceite", "corrigido")
            ]
            divisao= "val" if pasta not in so_treino and e_validacao(nome) else "train"
            for sub in ("images", "labels"):
                (saida / sub / divisao).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(pasta / "imagens" / tela["imagem"], saida / "images" / divisao / f"{nome}.jpg")
            (saida / "labels" / divisao / f"{nome}.txt").write_text("\n".join(linhas_yolo(itens)) + "\n", encoding="utf-8")
            imagens+= 1
            caixas+= len(itens)
            if copias_degradadas and divisao == "train":
                foto= cv2.imread(str(pasta / "imagens" / tela["imagem"]))
                rng= random.Random(nome)
                for k in range(copias_degradadas):
                    base= f"{nome}_d{k}"
                    cv2.imwrite(str(saida / "images" / divisao / f"{base}.jpg"), degradar_foto(rng, foto))
                    (saida / "labels" / divisao / f"{base}.txt").write_text(
                        "\n".join(linhas_yolo(itens)) + "\n", encoding="utf-8"
                    )
                    imagens+= 1
                    caixas+= len(itens)
            if com_ladrilhos and divisao == "train" and max(largura, altura) >= MINIMO_PARA_LADRILHAR:
                foto= cv2.imread(str(pasta / "imagens" / tela["imagem"]))
                em_pixeis= [(i, x0 * largura, y0 * altura, x1 * largura, y1 * altura) for i, x0, y0, x1, y1 in itens]
                for x, y, lx, ly, dentro in ladrilhos(largura, altura, em_pixeis):
                    base= f"{nome}_t{x}_{y}"
                    cv2.imwrite(str(saida / "images" / divisao / f"{base}.jpg"), foto[y : y + ly, x : x + lx])
                    (saida / "labels" / divisao / f"{base}.txt").write_text(
                        "\n".join(linhas_yolo(dentro)) + "\n", encoding="utf-8"
                    )
                    imagens+= 1
                    caixas+= len(dentro)
    escrever_data_yaml(saida, NOMES)
    return imagens, caixas


def main(argv: list[str] | None= None) -> int:
    parser= argparse.ArgumentParser(prog="python -m training.datasets.ouro")
    parser.add_argument("--pastas", nargs="+", required=True)
    parser.add_argument("--saida", default="data/datasets/ouro")
    parser.add_argument("--ladrilhos", action="store_true", help="also add 1024 px training tiles of big photos")
    parser.add_argument("--so-treino", nargs="*", default=[], help="folders only used for training (pseudo-labels)")
    parser.add_argument("--degradadas", type=int, default=0, help="blurred/compressed/dark copies of each train photo")
    args= parser.parse_args(argv)
    imagens, caixas= converter(
        [Path(p) for p in args.pastas], Path(args.saida), args.ladrilhos, args.degradadas, [Path(p) for p in args.so_treino]
    )
    print(f"{imagens} imagens, {caixas} caixas em {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
