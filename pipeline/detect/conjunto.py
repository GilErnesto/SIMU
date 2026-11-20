"""Ensemble of detectors: boxes several models agree on keep a high confidence, odd ones drop.

Each member's boxes are matched to the others' by IoU within a category. A group's confidence is the
mean over all members (a member that saw nothing counts as 0), its box the mean box, and its class the
one from its most confident member.
"""

from dataclasses import replace

import numpy as np

from pipeline.models import Detection

IOU_GRUPO= 0.5


def _iou(a, b) -> float:
    largura= min(a[2], b[2]) - max(a[0], b[0])
    altura= min(a[3], b[3]) - max(a[1], b[1])
    if largura <= 0 or altura <= 0:
        return 0.0
    intersecao= largura * altura
    return intersecao / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersecao)


def juntar(listas: list[list[Detection]], iou: float= IOU_GRUPO) -> list[Detection]:
    grupos: list[dict]= []
    for membro, deteccoes in enumerate(listas):
        for detecao in sorted(deteccoes, key=lambda d: d.confidence, reverse=True):
            candidatos= [
                g for g in grupos
                if g["categoria"] == detecao.category and membro not in g["membros"]
                and _iou(g["caixa"], detecao.bbox_xyxy) >= iou
            ]
            if candidatos:
                grupo= max(candidatos, key=lambda g: _iou(g["caixa"], detecao.bbox_xyxy))
                grupo["membros"][membro]= detecao
            else:
                grupos.append({"categoria": detecao.category, "caixa": detecao.bbox_xyxy, "membros": {membro: detecao}})
    saida= []
    for grupo in grupos:
        membros= list(grupo["membros"].values())
        melhor= max(membros, key=lambda d: d.confidence)
        caixa= tuple(float(v) for v in np.mean([d.bbox_xyxy for d in membros], axis=0))
        confianca= sum(d.confidence for d in membros) / len(listas)
        saida.append(replace(melhor, bbox_xyxy=caixa, confidence=confianca))
    return saida


class Conjunto:
    def __init__(self, detetores: list):
        self.detetores= detetores

    def detect(self, image_id: str, image: np.ndarray) -> list[Detection]:
        return juntar([detetor.detect(image_id, image) for detetor in self.detetores])


class PorCategoria:
    """Some categories from one detector, the rest from another."""

    def __init__(self, principal, outras, categorias_principal: frozenset[str]):
        self.principal= principal
        self.outras= outras
        self.categorias_principal= categorias_principal

    def detect(self, image_id: str, image: np.ndarray) -> list[Detection]:
        return [d for d in self.principal.detect(image_id, image) if d.category in self.categorias_principal] + [
            d for d in self.outras.detect(image_id, image) if d.category not in self.categorias_principal
        ]
