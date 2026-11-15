import math
from collections import defaultdict
from itertools import combinations

import numpy as np
from pyproj import Transformer

from pipeline.config import Classes, Municipio
from pipeline.geolocate.bearing import (
    horizontal_fov,
    monocular_distance,
    object_bearing,
    vertical_fov,
)
from pipeline.geolocate.dedup import cluster
from pipeline.geolocate.triangulate import (
    ALCANCE_MAX_M,
    DISTANCIA_MAX_ORIGENS_M,
    direction,
    intersect,
)
from pipeline.models import Detection, Element, ImageRecord, Observation


def _observe(detecao: Detection, imagem: ImageRecord) -> Observation:
    x1, _, x2, _= detecao.bbox_xyxy
    fov= horizontal_fov(imagem.camera_type)
    rumo= object_bearing(imagem.heading, (x1 + x2) / 2, imagem.width, fov)
    return Observation(detecao, imagem, rumo)


def _monocular(obs: Observation, origem: tuple[float, float], altura_m: float):
    imagem= obs.image
    _, y1, _, y2= obs.detection.bbox_xyxy
    fov_v= vertical_fov(imagem.camera_type, imagem.width, imagem.height)
    distancia= monocular_distance(altura_m, y2 - y1, imagem.height, fov_v)
    if distancia is None or distancia > ALCANCE_MAX_M:
        return None
    dx, dy= direction(obs.bearing)
    return origem[0] + distancia * dx, origem[1] + distancia * dy


def _candidates(observacoes, origens, altura_m):
    candidatos= []
    usadas= set()
    for i, j in combinations(range(len(observacoes)), 2):
        if observacoes[i].image.id == observacoes[j].image.id:
            continue
        if math.dist(origens[i], origens[j]) > DISTANCIA_MAX_ORIGENS_M:
            continue
        ponto= intersect(origens[i], observacoes[i].bearing, origens[j], observacoes[j].bearing)
        if ponto is not None:
            candidatos.append((ponto, {i, j}, "triangulacao"))
            usadas.update((i, j))
    for i, obs in enumerate(observacoes):
        if i not in usadas:
            ponto= _monocular(obs, origens[i], altura_m)
            if ponto is not None:
                candidatos.append((ponto, {i}, "monocular"))
    return candidatos


def locate(
    images: list[ImageRecord],
    detections: list[Detection],
    municipio: Municipio,
    classes: Classes,
) -> list[Element]:
    por_id= {imagem.id: imagem for imagem in images}
    para_metros= Transformer.from_crs("EPSG:4326", municipio.crs_metrico, always_xy=True)
    para_graus= Transformer.from_crs(municipio.crs_metrico, "EPSG:4326", always_xy=True)
    grupos= defaultdict(list)
    for detecao in detections:
        grupos[(detecao.category, detecao.class_name)].append(
            _observe(detecao, por_id[detecao.image_id])
        )
    elementos= []
    for (categoria, classe), observacoes in grupos.items():
        origens= [para_metros.transform(o.image.lon, o.image.lat) for o in observacoes]
        config= classes.categorias[categoria]
        candidatos= _candidates(observacoes, origens, config.altura_m)
        if not candidatos:
            continue
        pontos= np.array([c[0] for c in candidatos])
        rotulos= cluster(pontos, config.raio_dedup_m)
        for rotulo in sorted(set(rotulos.tolist())):
            membros= [c for c, r in zip(candidatos, rotulos) if r == rotulo]
            indices= sorted(set().union(*(m[1] for m in membros)))
            x, y= pontos[rotulos == rotulo].mean(axis=0)
            lon, lat= para_graus.transform(x, y)
            triangulado= any(m[2] == "triangulacao" for m in membros)
            incluidas= [observacoes[i] for i in indices]
            elementos.append(
                Element(
                    category=categoria,
                    class_name=classe,
                    lon=lon,
                    lat=lat,
                    obstruido=all(o.detection.obstruido for o in incluidas),
                    metodo_geo="triangulacao" if triangulado else "monocular",
                    observations=incluidas,
                )
            )
    return elementos
