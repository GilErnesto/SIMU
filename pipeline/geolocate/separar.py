from collections import defaultdict
from collections.abc import Callable
from itertools import combinations

import numpy as np
from scipy.optimize import linear_sum_assignment

from pipeline.geolocate.triangulate import ALCANCE_MAX_M, direction, intersect

IOU_DUPLICADA= 0.3
CUSTO_MAX_M= 5.0
CUSTO_PROIBIDO= 1e6
RAIO_FUSAO_M= 4.0

Membro= tuple[tuple[float, float], set[int], str]


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ix= max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy= max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter= ix * iy
    uniao= (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / uniao if uniao > 0 else 0.0


def _compativeis(a: str, b: str, gerais: set[str]) -> bool:
    return a == b or a in gerais or b in gerais


def _raiz(pai: dict[int, int], i: int) -> int:
    while pai[i] != i:
        pai[i]= pai[pai[i]]
        i= pai[i]
    return i


def _unidades(indices: list[int], observacoes: list, gerais: set[str]) -> dict[str, list[list[int]]]:
    por_imagem= defaultdict(list)
    for i in indices:
        por_imagem[observacoes[i].image.id].append(i)
    resultado= {}
    for imagem, lista in por_imagem.items():
        pai= {i: i for i in lista}
        for a, b in combinations(lista, 2):
            da, db= observacoes[a].detection, observacoes[b].detection
            if not _compativeis(da.class_name, db.class_name, gerais) or _iou(da.bbox_xyxy, db.bbox_xyxy) >= IOU_DUPLICADA:
                pai[_raiz(pai, a)]= _raiz(pai, b)
        unidades= defaultdict(list)
        for i in lista:
            unidades[_raiz(pai, i)].append(i)
        resultado[imagem]= list(unidades.values())
    return resultado


def _melhor(unidade: list[int], observacoes: list) -> int:
    return max(unidade, key=lambda i: observacoes[i].detection.confidence)


def _custo(i: int, posicao: tuple[float, float], observacoes: list, origens: list) -> float:
    dx, dy= direction(observacoes[i].bearing)
    rx, ry= posicao[0] - origens[i][0], posicao[1] - origens[i][1]
    if rx * dx + ry * dy <= 0:
        return CUSTO_PROIBIDO
    return abs(rx * dy - ry * dx)


def _posicao_final(
    indices: list[int],
    observacoes: list,
    origens: list,
    monocular: Callable,
    altura_m: float,
    alcance_m: float= ALCANCE_MAX_M,
) -> tuple[tuple[float, float], str] | None:
    melhores= {}
    for i in indices:
        imagem= observacoes[i].image.id
        if imagem not in melhores or observacoes[i].detection.confidence > observacoes[melhores[imagem]].detection.confidence:
            melhores[imagem]= i
    escolhidas= list(melhores.values())
    pontos= []
    for i, j in combinations(escolhidas, 2):
        ponto= intersect(origens[i], observacoes[i].bearing, origens[j], observacoes[j].bearing, alcance_m)
        if ponto is not None:
            pontos.append(ponto)
    if pontos:
        return tuple(np.median(np.array(pontos), axis=0)), "triangulacao"
    monoculares= [p for p in (monocular(observacoes[i], origens[i], altura_m) for i in escolhidas) if p is not None]
    if monoculares:
        return tuple(np.mean(np.array(monoculares), axis=0)), "monocular"
    return None


def separar_mesma_imagem(
    membros: list[Membro],
    observacoes: list,
    origens: list,
    gerais: set[str],
    monocular: Callable,
    altura_m: float,
    alcance_m: float= ALCANCE_MAX_M,
) -> list[list[Membro]]:
    indices= sorted(set().union(*(m[1] for m in membros)))
    por_imagem= _unidades(indices, observacoes, gerais)
    if max(len(u) for u in por_imagem.values()) < 2:
        return [membros]
    centro= tuple(np.mean([m[0] for m in membros], axis=0))

    def posicao_da(unidade: list[int]) -> tuple[float, float]:
        i= _melhor(unidade, observacoes)
        ponto= monocular(observacoes[i], origens[i], altura_m)
        return ponto if ponto is not None else centro

    ancora= max(por_imagem, key=lambda im: (len(por_imagem[im]), sum(observacoes[_melhor(u, observacoes)].detection.confidence for u in por_imagem[im])))
    sementes= [{"posicao": posicao_da(u), "indices": list(u)} for u in por_imagem[ancora]]
    for imagem in sorted((im for im in por_imagem if im != ancora), key=lambda im: -len(por_imagem[im])):
        unidades= por_imagem[imagem]
        custos= np.array(
            [[_custo(_melhor(u, observacoes), s["posicao"], observacoes, origens) for s in sementes] for u in unidades]
        )
        linhas, colunas= linear_sum_assignment(custos)
        atribuidas= set()
        for r, c in zip(linhas.tolist(), colunas.tolist()):
            if custos[r, c] <= CUSTO_MAX_M:
                sementes[c]["indices"].extend(unidades[r])
                atribuidas.add(r)
        for r, unidade in enumerate(unidades):
            if r not in atribuidas:
                sementes.append({"posicao": posicao_da(unidade), "indices": list(unidade)})
    saida= []
    for semente in sementes:
        final= _posicao_final(semente["indices"], observacoes, origens, monocular, altura_m, alcance_m)
        if final is not None:
            saida.append([(final[0], set(semente["indices"]), final[1])])
    return saida


def _centro(grupo: list[Membro]) -> np.ndarray:
    return np.mean([m[0] for m in grupo], axis=0)


def fundir_proximos(grupos: list[list[Membro]], observacoes: list, raio_m: float | None= None) -> list[list[Membro]]:
    raio= RAIO_FUSAO_M if raio_m is None else raio_m
    if raio <= 0 or len(grupos) < 2:
        return grupos
    centros= [_centro(g) for g in grupos]
    imagens= [{observacoes[i].image.id for m in g for i in m[1]} for g in grupos]
    pares= sorted(
        (float(np.hypot(*(centros[a] - centros[b]))), a, b)
        for a, b in combinations(range(len(grupos)), 2)
        if np.hypot(*(centros[a] - centros[b])) <= raio
    )
    pai= list(range(len(grupos)))

    def raiz(i: int) -> int:
        while pai[i] != i:
            pai[i]= pai[pai[i]]
            i= pai[i]
        return i

    for _, a, b in pares:
        ra, rb= raiz(a), raiz(b)
        if ra == rb or imagens[ra] & imagens[rb]:
            continue
        pai[rb]= ra
        imagens[ra]|= imagens[rb]
    fundidos= defaultdict(list)
    for i, grupo in enumerate(grupos):
        fundidos[raiz(i)].extend(grupo)
    return list(fundidos.values())
