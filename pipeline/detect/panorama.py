import math
from collections import defaultdict

import cv2
import numpy as np

from pipeline.models import Detection

FOV_VISTA= 90.0
PASSO_VISTA= 60.0
LADO_VISTA= 960
IOU_NMS= 0.5


def _projecao(lado: int):
    focal= lado / 2 / math.tan(math.radians(FOV_VISTA / 2))
    colunas, linhas= np.meshgrid(
        np.arange(lado, dtype=np.float64), np.arange(lado, dtype=np.float64)
    )
    alfa= np.arctan2(colunas - lado / 2, focal)
    gama= np.arctan2(lado / 2 - linhas, np.hypot(colunas - lado / 2, focal))
    return focal, alfa, gama


def views(panorama: np.ndarray, lado: int= LADO_VISTA):
    altura, largura= panorama.shape[:2]
    _, alfa, gama= _projecao(lado)
    linha= np.clip((0.5 - gama / np.pi) * altura, 0, altura - 1).astype(np.float32)
    for yaw in np.arange(0, 360, PASSO_VISTA):
        x= ((np.radians(yaw) + alfa) / (2 * np.pi) + 0.5) * largura
        mapa_x= np.mod(x, largura).astype(np.float32)
        yield float(yaw), cv2.remap(
            panorama, mapa_x, linha, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP
        )


def to_panorama(
    caixa: tuple[float, float, float, float],
    yaw: float,
    largura: int,
    altura: int,
    lado: int= LADO_VISTA,
) -> tuple[float, float, float, float] | None:
    x1, y1, x2, y2= caixa
    focal= lado / 2 / math.tan(math.radians(FOV_VISTA / 2))
    alfa1= math.degrees(math.atan2(x1 - lado / 2, focal))
    alfa2= math.degrees(math.atan2(x2 - lado / 2, focal))
    if alfa2 <= alfa1:
        return None
    x1p= (((yaw + alfa1) / 360 + 0.5) * largura) % largura
    x2p= x1p + (alfa2 - alfa1) / 360 * largura

    def latitude(u: float, v: float) -> float:
        gama= math.atan2(lado / 2 - v, math.hypot(u - lado / 2, focal))
        return (0.5 - gama / math.pi) * altura

    ys= [latitude(u, v) for u in (x1, x2) for v in (y1, y2)]
    y1p= max(min(ys), 0.0)
    y2p= min(max(ys), float(altura))
    if y2p <= y1p:
        return None
    return x1p, y1p, x2p, y2p


def _iou(a: tuple[float, float, float, float], b, largura: int) -> float:
    horizontal= 0.0
    for desvio in (-largura, 0.0, largura):
        horizontal= max(horizontal, min(a[2], b[2] + desvio) - max(a[0], b[0] + desvio))
    vertical= min(a[3], b[3]) - max(a[1], b[1])
    if horizontal <= 0 or vertical <= 0:
        return 0.0
    area_a= (a[2] - a[0]) * (a[3] - a[1])
    area_b= (b[2] - b[0]) * (b[3] - b[1])
    return horizontal * vertical / (area_a + area_b - horizontal * vertical)


def nms(deteccoes: list[Detection], largura: int, iou: float= IOU_NMS) -> list[Detection]:
    por_classe= defaultdict(list)
    for detecao in deteccoes:
        por_classe[detecao.category].append(detecao)
    mantidas= []
    for lista in por_classe.values():
        escolhidas= []
        for detecao in sorted(lista, key=lambda d: d.confidence, reverse=True):
            if all(_iou(detecao.bbox_xyxy, outra.bbox_xyxy, largura) <= iou for outra in escolhidas):
                escolhidas.append(detecao)
        mantidas.extend(escolhidas)
    return mantidas


def detect_panorama(
    detector, image_id: str, panorama: np.ndarray, lado: int= LADO_VISTA
) -> list[Detection]:
    altura, largura= panorama.shape[:2]
    deteccoes= []
    for yaw, vista in views(panorama, lado):
        for detecao in detector.detect(image_id, vista):
            caixa= to_panorama(detecao.bbox_xyxy, yaw, largura, altura, lado)
            if caixa is None:
                continue
            deteccoes.append(
                Detection(
                    image_id,
                    detecao.category,
                    detecao.class_name,
                    caixa,
                    detecao.confidence,
                    detecao.obstruido,
                )
            )
    return nms(deteccoes, largura)
