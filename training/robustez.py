"""Robustness test for the sign-type head: type accuracy on degraded crops of the gold set.

Each reviewed crop of the test set is degraded in a fixed way (blur, motion blur, rotation, few pixels,
bad JPEG, dark, occlusion, cut by the border) and the head is scored on each version.
Types are compared by official category (STOP counts as cedência).

    python -m training.robustez --cabecas models/tipo_sinal.npz models/tipo_sinal_b3.npz
"""

import argparse
from argparse import Namespace
from pathlib import Path

import cv2
import numpy as np

from pipeline.config import load_classes
from pipeline.detect.cabeca import Cabeca
from training.tipos import LOTE
from training.tipos_web import recortes_revistos


def _movimento(imagem: np.ndarray, comprimento: int= 7) -> np.ndarray:
    nucleo= np.zeros((comprimento, comprimento), np.float32)
    nucleo[comprimento // 2, :]= 1.0 / comprimento
    return cv2.filter2D(imagem, -1, nucleo)


def _rodar(imagem: np.ndarray, graus: float) -> np.ndarray:
    altura, largura= imagem.shape[:2]
    matriz= cv2.getRotationMatrix2D((largura / 2, altura / 2), graus, 1.0)
    return cv2.warpAffine(imagem, matriz, (largura, altura), borderMode=cv2.BORDER_REPLICATE)


def _pixeis(imagem: np.ndarray, lado: int) -> np.ndarray:
    altura, largura= imagem.shape[:2]
    escala= lado / max(altura, largura)
    if escala >= 1:
        return imagem
    pequena= cv2.resize(imagem, (max(2, round(largura * escala)), max(2, round(altura * escala))), interpolation=cv2.INTER_AREA)
    return cv2.resize(pequena, (largura, altura), interpolation=cv2.INTER_LINEAR)


def _jpeg(imagem: np.ndarray, qualidade: int) -> np.ndarray:
    _, codificada= cv2.imencode(".jpg", imagem, [cv2.IMWRITE_JPEG_QUALITY, qualidade])
    return cv2.imdecode(codificada, cv2.IMREAD_COLOR)


def _tapar(imagem: np.ndarray) -> np.ndarray:
    saida= imagem.copy()
    largura= saida.shape[1]
    x= largura // 2 - largura // 8
    cv2.rectangle(saida, (x, 0), (x + max(1, largura // 4), saida.shape[0]), (60, 60, 60), -1)
    return saida


DEGRADACOES= {
    "original": lambda im: im,
    "desfocada": lambda im: cv2.GaussianBlur(im, (0, 0), 2.0),
    "movimento": _movimento,
    "rodada 20°": lambda im: _rodar(im, 20),
    "16 px": lambda im: _pixeis(im, 16),
    "10 px": lambda im: _pixeis(im, 10),
    "jpeg 15": lambda im: _jpeg(im, 15),
    "escura": lambda im: (im.astype(np.float32) * 0.35).astype(np.uint8),
    "poste à frente": _tapar,
    "cortada 30%": lambda im: im[:, : max(2, int(im.shape[1] * 0.7))],
}


def medir(cabeca: Cabeca, incorporar, recortes: list[tuple[str, np.ndarray]], familia: dict[str, str]) -> dict[str, float]:
    reais= [familia.get(c, c) for c, _ in recortes]
    resultado= {}
    for nome, degradar in DEGRADACOES.items():
        imagens= [degradar(r) for _, r in recortes]
        X= np.vstack([incorporar(imagens[i : i + LOTE]) for i in range(0, len(imagens), LOTE)])
        previstas= [familia.get(c, c) for c, _ in cabeca.prever(X)]
        resultado[nome]= sum(p == r for p, r in zip(previstas, reais, strict=True)) / len(reais)
    return resultado


def main(argv: list[str] | None= None) -> int:
    from training.tipos import _carregar_modelo

    parser= argparse.ArgumentParser(prog="python -m training.robustez")
    parser.add_argument("--cabecas", nargs="+", required=True)
    parser.add_argument("--teste", default="data/ouro")
    parser.add_argument("--classes", default="config/classes.yaml")
    args= parser.parse_args(argv)
    familia= load_classes(Path(args.classes)).categorias["sinal"].superclasse
    incorporar, _= _carregar_modelo(Namespace(classes=args.classes))
    recortes= recortes_revistos(Path(args.teste))
    tabelas= {c: medir(Cabeca.carregar(Path(c)), incorporar, recortes, familia) for c in args.cabecas}
    print(f"{len(recortes)} recortes de {args.teste}; tipo certo por categoria oficial\n")
    print("| Degradação | " + " | ".join(Path(c).name for c in args.cabecas) + " |")
    print("|---|" + "---|" * len(args.cabecas))
    for nome in DEGRADACOES:
        print(f"| {nome} | " + " | ".join(f"{tabelas[c][nome]:.0%}" for c in args.cabecas) + " |")
    medias= [np.mean(list(tabelas[c].values())) for c in args.cabecas]
    print("| **média** | " + " | ".join(f"**{m:.0%}**" for m in medias) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
