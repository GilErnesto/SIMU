import math
from collections import defaultdict

import cv2
import numpy as np

from pipeline.models import Detection

FOV_VISTA= 90.0
PASSO_VISTA= 60.0
LADO_VISTA= 960
IOU_NMS= 0.5
DENTRO_NMS= 0.7
ALTURA_MIN_INCLINADA= 0.2
IOU_INCLINADA= 0.2
DENTRO_INCLINADA= 0.5
CONFIANCA_MIN_INCLINADA= 0.6


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


def _direcoes(lado: int, yaw: float, pitch: float):
    focal= lado / 2 / math.tan(math.radians(FOV_VISTA / 2))
    colunas, linhas= np.meshgrid(np.arange(lado, dtype=np.float64), np.arange(lado, dtype=np.float64))
    x, y= colunas - lado / 2, lado / 2 - linhas
    p= math.radians(pitch)
    y2= y * math.cos(p) + focal * math.sin(p)
    z2= -y * math.sin(p) + focal * math.cos(p)
    return math.radians(yaw) + np.arctan2(x, z2), np.arctan2(y2, np.hypot(x, z2))


def views_inclinadas(panorama: np.ndarray, pitch: float, lado: int= LADO_VISTA):
    altura, largura= panorama.shape[:2]
    for yaw in np.arange(0, 360, PASSO_VISTA):
        lon, lat= _direcoes(lado, float(yaw), pitch)
        mapa_x= np.mod((lon / (2 * np.pi) + 0.5) * largura, largura).astype(np.float32)
        mapa_y= np.clip((0.5 - lat / np.pi) * altura, 0, altura - 1).astype(np.float32)
        yield float(yaw), cv2.remap(panorama, mapa_x, mapa_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)


def _caixa_inclinada(
    caixa: tuple[float, float, float, float], yaw: float, pitch: float, largura: int, altura: int, lado: int
) -> tuple[float, float, float, float] | None:
    x1, y1, x2, y2= caixa
    focal= lado / 2 / math.tan(math.radians(FOV_VISTA / 2))
    p= math.radians(pitch)
    longitudes= []
    latitudes= []
    for u in (x1, (x1 + x2) / 2, x2):
        for v in (y1, (y1 + y2) / 2, y2):
            x, y= u - lado / 2, lado / 2 - v
            y2d= y * math.cos(p) + focal * math.sin(p)
            z2d= -y * math.sin(p) + focal * math.cos(p)
            longitudes.append(yaw + math.degrees(math.atan2(x, z2d)))
            latitudes.append(math.degrees(math.atan2(y2d, math.hypot(x, z2d))))
    centro= longitudes[4]
    meia= max(abs(longitude - centro) for longitude in longitudes)
    if meia <= 0:
        return None
    x1p= (((centro - meia) / 360 + 0.5) * largura) % largura
    x2p= x1p + 2 * meia / 360 * largura
    y1p= max((0.5 - max(latitudes) / 180) * altura, 0.0)
    y2p= min((0.5 - min(latitudes) / 180) * altura, float(altura))
    if y2p <= y1p:
        return None
    return x1p, y1p, x2p, y2p


def to_panorama(
    caixa: tuple[float, float, float, float],
    yaw: float,
    largura: int,
    altura: int,
    lado: int= LADO_VISTA,
    pitch: float= 0.0,
) -> tuple[float, float, float, float] | None:
    if pitch:
        return _caixa_inclinada(caixa, yaw, pitch, largura, altura, lado)
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


def _intersecao(a: tuple[float, float, float, float], b, largura: int) -> float:
    horizontal= 0.0
    for desvio in (-largura, 0.0, largura):
        horizontal= max(horizontal, min(a[2], b[2] + desvio) - max(a[0], b[0] + desvio))
    vertical= min(a[3], b[3]) - max(a[1], b[1])
    if horizontal <= 0 or vertical <= 0:
        return 0.0
    return horizontal * vertical


def _iou(a: tuple[float, float, float, float], b, largura: int) -> float:
    inter= _intersecao(a, b, largura)
    if inter <= 0:
        return 0.0
    area_a= (a[2] - a[0]) * (a[3] - a[1])
    area_b= (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


def _dentro(a: tuple[float, float, float, float], b, largura: int) -> float:
    area_a= (a[2] - a[0]) * (a[3] - a[1])
    return _intersecao(a, b, largura) / area_a if area_a > 0 else 0.0


def nms(deteccoes: list[Detection], largura: int, iou: float= IOU_NMS, dentro: float= DENTRO_NMS) -> list[Detection]:
    por_classe= defaultdict(list)
    for detecao in deteccoes:
        por_classe[detecao.category].append(detecao)
    mantidas= []
    for lista in por_classe.values():
        escolhidas= []
        for detecao in sorted(lista, key=lambda d: d.confidence, reverse=True):
            if all(
                _iou(detecao.bbox_xyxy, outra.bbox_xyxy, largura) <= iou
                and _dentro(detecao.bbox_xyxy, outra.bbox_xyxy, largura) < dentro
                for outra in escolhidas
            ):
                escolhidas.append(detecao)
        mantidas.extend(escolhidas)
    return mantidas


def _deteccoes_das_vistas(detector, image_id: str, vistas, pitch: float, largura: int, altura: int, lado: int, categorias):
    resultado= []
    for yaw, vista in vistas:
        for detecao in detector.detect(image_id, vista):
            if categorias is not None and detecao.category not in categorias:
                continue
            caixa= to_panorama(detecao.bbox_xyxy, yaw, largura, altura, lado, pitch)
            if caixa is None:
                continue
            resultado.append(
                Detection(image_id, detecao.category, detecao.class_name, caixa, detecao.confidence, detecao.obstruido)
            )
    return resultado


def deteccoes_inclinadas(
    detector, image_id: str, panorama: np.ndarray, inclinadas: dict[float, frozenset[str]], lado: int= LADO_VISTA
) -> list[Detection]:
    altura, largura= panorama.shape[:2]
    resultado= []
    for pitch, categorias in inclinadas.items():
        resultado.extend(
            _deteccoes_das_vistas(
                detector, image_id, views_inclinadas(panorama, pitch, lado), pitch, largura, altura, lado, categorias
            )
        )
    return resultado


def juntar_inclinadas(
    base: list[Detection],
    inclinadas: list[Detection],
    largura: int,
    altura: int,
    altura_min: float= ALTURA_MIN_INCLINADA,
    confianca_min: float= CONFIANCA_MIN_INCLINADA,
) -> list[Detection]:
    extra= []
    for detecao in nms(inclinadas, largura):
        caixa= detecao.bbox_xyxy
        if (caixa[3] - caixa[1]) / altura < altura_min or detecao.confidence < confianca_min:
            continue
        if any(
            outra.category == detecao.category
            and (
                _iou(caixa, outra.bbox_xyxy, largura) > IOU_INCLINADA
                or _dentro(caixa, outra.bbox_xyxy, largura) >= DENTRO_INCLINADA
                or _dentro(outra.bbox_xyxy, caixa, largura) >= DENTRO_INCLINADA
            )
            for outra in base
        ):
            continue
        extra.append(detecao)
    return base + extra


def detect_panorama(
    detector,
    image_id: str,
    panorama: np.ndarray,
    lado: int= LADO_VISTA,
    inclinadas: dict[float, frozenset[str]] | None= None,
) -> list[Detection]:
    altura, largura= panorama.shape[:2]
    base= nms(_deteccoes_das_vistas(detector, image_id, views(panorama, lado), 0.0, largura, altura, lado, None), largura)
    if not inclinadas:
        return base
    return juntar_inclinadas(base, deteccoes_inclinadas(detector, image_id, panorama, inclinadas, lado), largura, altura)
