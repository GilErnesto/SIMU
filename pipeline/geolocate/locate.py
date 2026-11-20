import math
from collections import Counter, defaultdict
from functools import partial
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
from pipeline.geolocate.minimos import ponto_minimos_quadrados
from pipeline.geolocate.seguir import ordem_dos_frames, trilhos
from pipeline.geolocate.separar import fundir_proximos, separar_mesma_imagem
from pipeline.geolocate.triangulate import (
    ALCANCE_MAX_M,
    DISTANCIA_MAX_ORIGENS_M,
    direction,
    intersect,
)
from pipeline.models import Detection, Element, ImageRecord, Observation


def _observe(detecao: Detection, imagem: ImageRecord) -> Observation:
    x1, _, x2, _= detecao.bbox_xyxy
    fov= horizontal_fov(imagem.camera_type, imagem.width, imagem.height)
    rumo= object_bearing(imagem.heading, (x1 + x2) / 2, imagem.width, fov)
    return Observation(detecao, imagem, rumo)


def _monocular(
    obs: Observation,
    origem: tuple[float, float],
    altura_m: float,
    alcance_m: float= ALCANCE_MAX_M,
    alturas: dict[str, float] | None= None,
):
    imagem= obs.image
    altura_m= (alturas or {}).get(obs.detection.class_name, altura_m)
    _, y1, _, y2= obs.detection.bbox_xyxy
    fov_v= vertical_fov(imagem.camera_type, imagem.width, imagem.height)
    distancia= monocular_distance(altura_m, y2 - y1, imagem.height, fov_v)
    if distancia is None or distancia > alcance_m:
        return None
    dx, dy= direction(obs.bearing)
    return origem[0] + distancia * dx, origem[1] + distancia * dy


def _candidates(observacoes, origens, altura_m, alcance_m, alturas= None):
    candidatos= []
    usadas= set()
    for i, j in combinations(range(len(observacoes)), 2):
        if observacoes[i].image.id == observacoes[j].image.id:
            continue
        if math.dist(origens[i], origens[j]) > DISTANCIA_MAX_ORIGENS_M:
            continue
        ponto= intersect(origens[i], observacoes[i].bearing, origens[j], observacoes[j].bearing, alcance_m)
        if ponto is not None:
            candidatos.append((ponto, {i, j}, "triangulacao"))
            usadas.update((i, j))
    for i, obs in enumerate(observacoes):
        if i not in usadas:
            ponto= _monocular(obs, origens[i], altura_m, alcance_m, alturas)
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


def _repartir(
    gerais: set[str], observacoes: list[Observation], exclusivos: bool= False
) -> list[tuple[str, list[Observation]]]:
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
    if exclusivos:
        return [(topo, list(observacoes))]
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
        ponto= _monocular(obs, origens[i], config.altura_m, config.alcance_max_m, config.alturas_por_classe)
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


USAR_MINIMOS_QUADRADOS= False


def _posicao(membros, observacoes, origens) -> tuple[float, float]:
    media= tuple(np.mean([m[0] for m in membros], axis=0))
    if not USAR_MINIMOS_QUADRADOS:
        return media
    indices= sorted(_indices_de([m for m in membros if m[2] == "triangulacao"]))
    if _imagens(indices, observacoes) < 2:
        return media
    ponto= ponto_minimos_quadrados(
        [origens[i] for i in indices], [observacoes[i].bearing for i in indices]
    )
    return media if ponto is None else ponto


FONTE_VIDEO= "video"
MIN_CAIXAS_TRILHO= 2
ABERTURA_MIN_GRAUS= 10.0


def _abertura(rumos: list[float]) -> float:
    relativos= [(r - rumos[0] + 180) % 360 - 180 for r in rumos]
    return max(relativos) - min(relativos)


def _grupos_por_trilhos(observacoes, origens, config, frames):
    grupos= []
    dentro= set()
    for indices in trilhos(observacoes, frames):
        if len(indices) < MIN_CAIXAS_TRILHO:
            continue
        monoculares= {
            i: _monocular(observacoes[i], origens[i], config.altura_m, config.alcance_max_m, config.alturas_por_classe)
            for i in indices
        }
        perto= [i for i, ponto in monoculares.items() if ponto is not None]
        if not perto:
            continue
        rumos= [observacoes[i].bearing for i in perto]
        ponto= None
        if len(perto) >= 2 and _abertura(rumos) >= ABERTURA_MIN_GRAUS:
            ponto= ponto_minimos_quadrados([origens[i] for i in perto], rumos)
            if ponto is not None and min(math.dist(ponto, origens[i]) for i in perto) > config.alcance_max_m:
                ponto= None
        metodo= "triangulacao"
        if ponto is None:
            ponto= tuple(np.mean([monoculares[i] for i in perto], axis=0))
            metodo= "monocular"
        dentro.update(perto)
        grupos.append([(ponto, set(indices), metodo)])
    fundidos= fundir_proximos(grupos, observacoes, config.raio_dedup_m)
    return [[(ponto, indices & dentro, metodo) for ponto, indices, metodo in grupo] for grupo in fundidos]


def _elementos(categoria, grupos_c, observacoes, origens, config, para_graus) -> list[Element]:
    elementos= []
    for membros in grupos_c:
        indices= sorted(set().union(*(m[1] for m in membros)))
        x, y= _posicao(membros, observacoes, origens)
        lon, lat= para_graus.transform(x, y)
        triangulado= any(m[2] == "triangulacao" for m in membros)
        incluidas= [observacoes[i] for i in indices]
        for classe, da_classe in _repartir(set(config.gerais), incluidas, config.tipos_exclusivos):
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


def _area(caixa: tuple[float, float, float, float]) -> float:
    return max(caixa[2] - caixa[0], 0.0) * max(caixa[3] - caixa[1], 0.0)


def _contida(menor: Detection, maior: Detection, fracao: float) -> bool:
    a, b= menor.bbox_xyxy, maior.bbox_xyxy
    area= _area(a)
    if area <= 0 or area >= _area(b) or menor.confidence > maior.confidence:
        return False
    dentro= _area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))
    return dentro / area >= fracao


def suprimir_contidas(detections: list[Detection], classes: Classes) -> list[Detection]:
    por_grupo= defaultdict(list)
    for detecao in detections:
        por_grupo[(detecao.image_id, detecao.category)].append(detecao)
    resultado= []
    for (_, categoria), lista in por_grupo.items():
        fracao= classes.categorias[categoria].suprimir_contidas
        if fracao is None:
            resultado.extend(lista)
            continue
        resultado.extend(
            d for d in lista if not any(_contida(d, outra, fracao) for outra in lista if outra is not d)
        )
    return resultado


def locate(
    images: list[ImageRecord],
    detections: list[Detection],
    municipio: Municipio,
    classes: Classes,
) -> list[Element]:
    detections= suprimir_contidas(detections, classes)
    por_id= {imagem.id: imagem for imagem in images}
    para_metros= Transformer.from_crs("EPSG:4326", municipio.crs_metrico, always_xy=True)
    para_graus= Transformer.from_crs(municipio.crs_metrico, "EPSG:4326", always_xy=True)
    grupos= defaultdict(list)
    elementos= []
    frames= ordem_dos_frames([i for i in images if i.fonte == FONTE_VIDEO and i.localizavel])
    for detecao in detections:
        imagem= por_id[detecao.image_id]
        if imagem.localizavel:
            grupos[detecao.category].append(_observe(detecao, imagem))
        else:
            elementos.append(_sem_posicao(detecao, imagem))
    for categoria, observacoes in grupos.items():
        config= classes.categorias[categoria]
        if config.seguir_video:
            de_video= [o for o in observacoes if o.image.fonte == FONTE_VIDEO]
            if de_video:
                origens_v= [para_metros.transform(o.image.lon, o.image.lat) for o in de_video]
                grupos_v= _grupos_por_trilhos(de_video, origens_v, config, frames)
                elementos.extend(_elementos(categoria, grupos_v, de_video, origens_v, config, para_graus))
            observacoes= [o for o in observacoes if o.image.fonte != FONTE_VIDEO]
        origens= [para_metros.transform(o.image.lon, o.image.lat) for o in observacoes]
        candidatos= _candidates(observacoes, origens, config.altura_m, config.alcance_max_m, config.alturas_por_classe)
        if not candidatos:
            continue
        pontos= np.array([c[0] for c in candidatos])
        rotulos= cluster(pontos, config.raio_dedup_m)
        grupos_c= [
            [c for c, r in zip(candidatos, rotulos) if r == rotulo] for rotulo in sorted(set(rotulos.tolist()))
        ]
        grupos_c= _consenso(grupos_c, observacoes, origens, config)
        monocular= partial(_monocular, alcance_m=config.alcance_max_m, alturas=config.alturas_por_classe)
        compativeis= set(config.classes if config.tipos_exclusivos else config.gerais)
        grupos_c= [
            separado
            for membros in grupos_c
            for separado in separar_mesma_imagem(
                membros, observacoes, origens, compativeis, monocular, config.altura_m, config.alcance_max_m
            )
        ]
        grupos_c= fundir_proximos(grupos_c, observacoes, config.raio_dedup_m)
        elementos.extend(_elementos(categoria, grupos_c, observacoes, origens, config, para_graus))
    return elementos
