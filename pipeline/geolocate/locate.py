import math
from collections import Counter, defaultdict
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


SEM_POSICAO= "sem_posicao"


def _sem_posicao(detecao: Detection, imagem: ImageRecord) -> Element:
    return Element(
        category=detecao.category,
        class_name=detecao.class_name,
        lon=None,
        lat=None,
        obstruido=detecao.obstruido,
        metodo_geo=SEM_POSICAO,
        observations=[Observation(detecao, imagem, None)],
    )


MIN_IMAGENS_SECUNDARIA= 2
FRACAO_SECUNDARIA= 0.4


def _repartir(gerais: set[str], observacoes: list[Observation]) -> list[tuple[str, list[Observation]]]:
    pesos= defaultdict(float)
    imagens= defaultdict(set)
    por_imagem= defaultdict(set)
    for obs in observacoes:
        classe= obs.detection.class_name
        if classe in gerais:
            continue
        pesos[classe]+= obs.detection.confidence
        imagens[classe].add(obs.image.id)
        por_imagem[obs.image.id].add(classe)
    if not pesos:
        classe= Counter(o.detection.class_name for o in observacoes).most_common(1)[0][0]
        return [(classe, list(observacoes))]
    topo= max(pesos, key=pesos.get)
    minimo= max(MIN_IMAGENS_SECUNDARIA, math.ceil(FRACAO_SECUNDARIA * len(imagens[topo])))
    validas= {topo}
    for classe in pesos:
        juntas= any(classe in classes and len(classes) > 1 for classes in por_imagem.values())
        if len(imagens[classe]) >= minimo or juntas:
            validas.add(classe)
    grupos= defaultdict(list)
    for obs in observacoes:
        classe= obs.detection.class_name
        grupos[classe if classe in validas else topo].append(obs)
    return list(grupos.items())


TOLERANCIA_RAIO_M= 1.5


def _passa_perto(obs, origem, ponto, tolerancia_m: float) -> bool:
    dx, dy= direction(obs.bearing)
    rx, ry= ponto[0] - origem[0], ponto[1] - origem[1]
    return rx * dx + ry * dy > 0 and abs(rx * dy - ry * dx) <= tolerancia_m


def _imagens(indices, observacoes) -> int:
    return len({observacoes[i].image.id for i in indices})


def _indices_de(membros) -> set:
    return set().union(*(m[1] for m in membros))


def _melhor_ponto(pares, livres, observacoes, origens):
    melhor= None
    for par in pares:
        apoio= {i for i in livres if _passa_perto(observacoes[i], origens[i], par[0], TOLERANCIA_RAIO_M)}
        chave= (_imagens(apoio, observacoes), len(apoio))
        if chave[0] >= 2 and (melhor is None or chave > melhor[0]):
            melhor= (chave, par, apoio)
    return melhor


def _consenso(grupos, observacoes, origens, config):
    ordem= sorted(grupos, key=lambda m: -_imagens(_indices_de(m), observacoes))
    usadas= set()
    mantidos= []
    for membros in ordem:
        pares= [m for m in membros if m[2] == "triangulacao"]
        livres= _indices_de(membros) - usadas
        if not pares:
            ficam= [m for m in membros if m[1] <= livres]
            if ficam:
                mantidos.append(ficam)
                usadas|= _indices_de(ficam)
            continue
        centro= np.mean([m[0] for m in membros], axis=0)
        perto= {i for i in livres if _passa_perto(observacoes[i], origens[i], centro, TOLERANCIA_RAIO_M)}
        ficam= [m for m in membros if m[1] <= perto]
        if any(m[2] == "triangulacao" for m in ficam):
            mantidos.append(ficam)
            usadas|= _indices_de(ficam)
            continue
        while True:
            melhor= _melhor_ponto(pares, livres, observacoes, origens)
            if melhor is None:
                break
            _, par, apoio= melhor
            ficam= [m for m in pares if m[1] <= apoio]
            ficam+= [(par[0], {i}, "triangulacao") for i in apoio - _indices_de(ficam)]
            mantidos.append(ficam)
            livres-= apoio
            usadas|= apoio
    soltas= []
    for i, obs in enumerate(observacoes):
        if i in usadas:
            continue
        ponto= _monocular(obs, origens[i], config.altura_m)
        if ponto is not None:
            soltas.append((ponto, {i}, "monocular"))
    if soltas:
        centros= np.array([np.mean([m[0] for m in g], axis=0) for g in mantidos]) if mantidos else None
        isoladas= []
        for s in soltas:
            if centros is not None:
                d= np.hypot(*(centros - np.array(s[0])).T)
                if d.min() <= config.raio_dedup_m:
                    mantidos[int(d.argmin())].append(s)
                    continue
            isoladas.append(s)
        if isoladas:
            rotulos= cluster(np.array([s[0] for s in isoladas]), config.raio_dedup_m)
            for rotulo in sorted(set(rotulos.tolist())):
                mantidos.append([s for s, r in zip(isoladas, rotulos) if r == rotulo])
    return mantidos


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
    elementos= []
    for detecao in detections:
        imagem= por_id[detecao.image_id]
        if imagem.localizavel:
            grupos[detecao.category].append(_observe(detecao, imagem))
        else:
            elementos.append(_sem_posicao(detecao, imagem))
    for categoria, observacoes in grupos.items():
        origens= [para_metros.transform(o.image.lon, o.image.lat) for o in observacoes]
        config= classes.categorias[categoria]
        candidatos= _candidates(observacoes, origens, config.altura_m)
        if not candidatos:
            continue
        pontos= np.array([c[0] for c in candidatos])
        rotulos= cluster(pontos, config.raio_dedup_m)
        grupos_c= [
            [c for c, r in zip(candidatos, rotulos) if r == rotulo] for rotulo in sorted(set(rotulos.tolist()))
        ]
        grupos_c= _consenso(grupos_c, observacoes, origens, config)
        for membros in grupos_c:
            indices= sorted(set().union(*(m[1] for m in membros)))
            x, y= np.mean([m[0] for m in membros], axis=0)
            lon, lat= para_graus.transform(x, y)
            triangulado= any(m[2] == "triangulacao" for m in membros)
            incluidas= [observacoes[i] for i in indices]
            for classe, da_classe in _repartir(set(config.gerais), incluidas):
                elementos.append(
                    Element(
                        category=categoria,
                        class_name=classe,
                        lon=lon,
                        lat=lat,
                        obstruido=all(o.detection.obstruido for o in da_classe),
                        metodo_geo="triangulacao" if triangulado else "monocular",
                        observations=da_classe,
                    )
                )
    return elementos
