from collections import defaultdict

import numpy as np
from scipy.optimize import linear_sum_assignment

from pipeline.models import ImageRecord, Observation

FALHAS_MAX= 2
INTERVALO_MAX_S= 3.0
DESVIO_MAX_LARGURAS= 1.5
ESCALA_MAX= 1.6
PESO_CENTRO= 0.3
SEM_PAR= 1e6


def _iou(a: tuple, b: tuple) -> float:
    ix= max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy= max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter= ix * iy
    uniao= (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / uniao if uniao > 0 else 0.0


def _custo(a: tuple, b: tuple, passos: int) -> float:
    largura= max(a[2] - a[0], b[2] - b[0], 1e-6)
    desvio= abs((a[0] + a[2]) / 2 - (b[0] + b[2]) / 2) / largura
    alturas= sorted((a[3] - a[1], b[3] - b[1]))
    escala= alturas[1] / max(alturas[0], 1e-6)
    if desvio > DESVIO_MAX_LARGURAS * passos or escala > ESCALA_MAX**passos:
        return SEM_PAR
    return 1 - _iou(a, b) + PESO_CENTRO * desvio


def ordem_dos_frames(imagens: list[ImageRecord]) -> list[ImageRecord]:
    return sorted(imagens, key=lambda i: (i.capturada_em is None, i.capturada_em or 0, i.id_fonte))


def trilhos(observacoes: list[Observation], frames: list[ImageRecord] | None= None) -> list[list[int]]:
    por_imagem= defaultdict(list)
    for indice, obs in enumerate(observacoes):
        por_imagem[obs.image.id].append(indice)
    if frames is None:
        frames= ordem_dos_frames(list({o.image.id: o.image for o in observacoes}.values()))
    feitos= []
    ativos= []
    anterior= None
    for n, imagem in enumerate(frames):
        if (
            anterior is not None
            and imagem.capturada_em is not None
            and anterior.capturada_em is not None
            and (imagem.capturada_em - anterior.capturada_em).total_seconds() > INTERVALO_MAX_S
        ):
            ativos= []
        anterior= imagem
        ativos= [t for t in ativos if n - t["ultimo"] <= FALHAS_MAX + 1]
        indices= por_imagem.get(imagem.id, [])
        if not indices:
            continue
        custos= np.array(
            [[_custo(t["caixa"], observacoes[i].detection.bbox_xyxy, n - t["ultimo"]) for i in indices] for t in ativos]
        ).reshape(len(ativos), len(indices))
        ligados= set()
        if ativos:
            for linha, coluna in zip(*linear_sum_assignment(custos), strict=True):
                if custos[linha, coluna] < SEM_PAR:
                    trilho= ativos[linha]
                    trilho["indices"].append(indices[coluna])
                    trilho["caixa"]= observacoes[indices[coluna]].detection.bbox_xyxy
                    trilho["ultimo"]= n
                    ligados.add(coluna)
        for coluna, indice in enumerate(indices):
            if coluna not in ligados:
                trilho= {"indices": [indice], "caixa": observacoes[indice].detection.bbox_xyxy, "ultimo": n}
                feitos.append(trilho)
                ativos.append(trilho)
    return [t["indices"] for t in feitos]
