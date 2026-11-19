import math
import random
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pyproj import Transformer

from pipeline.config import load_classes, load_municipio
from pipeline.geolocate import locate as L
from pipeline.geolocate.bearing import horizontal_fov, vertical_fov
from pipeline.geolocate.locate import _observe, locate
from pipeline.geolocate.seguir import trilhos
from pipeline.models import Detection, ImageRecord

CONFIG= Path(__file__).parents[1] / "config"
MUNICIPIO= load_municipio(CONFIG / "municipio.yaml")
CLASSES= load_classes(CONFIG / "classes.yaml")
PARA_GRAUS= Transformer.from_crs(MUNICIPIO.crs_metrico, "EPSG:4326", always_xy=True)
PARA_METROS= Transformer.from_crs("EPSG:4326", MUNICIPIO.crs_metrico, always_xy=True)
LARGURA, ALTURA= 1080, 1920
INICIO= datetime(2026, 11, 19, 10, tzinfo=UTC)


def _origem():
    lon_min, lat_min, lon_max, lat_max= MUNICIPIO.bbox
    return PARA_METROS.transform((lon_min + lon_max) / 2, (lat_min + lat_max) / 2)


def _frame(n, x, y, segundos):
    lon, lat= PARA_GRAUS.transform(x, y)
    return ImageRecord(
        "video", f"v-{n:05d}", "u", "l", "", INICIO + timedelta(seconds=segundos), lon, lat, 0.0,
        "perspective", "", width=LARGURA, height=ALTURA,
    )


def _caixa(frame, origem, poste):
    dx, dy= poste[0] - origem[0], poste[1] - origem[1]
    distancia= math.hypot(dx, dy)
    relativo= math.degrees(math.atan2(dx, dy)) - frame.heading
    fov= horizontal_fov("perspective", LARGURA, ALTURA)
    if abs(relativo) > fov / 2 - 1 or not 8 <= distancia <= 30:
        return None
    centro= (relativo / fov + 0.5) * LARGURA
    altura= math.degrees(2 * math.atan(6 / (2 * distancia))) / vertical_fov("perspective", LARGURA, ALTURA) * ALTURA
    return Detection(frame.id, "iluminacao", "poste_luz", (centro - 15, 900 - altura / 2, centro + 15, 900 + altura / 2), 0.9, False)


def _video(postes, passos=30, passo_m=0.75, ruido=None):
    x0, y0= _origem()
    frames, deteccoes= [], []
    for n in range(passos):
        origem= (x0, y0 + n * passo_m)
        frame= _frame(n, *origem, n * 0.5)
        frames.append(frame)
        for poste in postes:
            caixa= _caixa(frame, origem, (x0 + poste[0], y0 + poste[1]))
            if caixa is None:
                continue
            if ruido is not None:
                x1, y1, x2, y2= caixa.bbox_xyxy
                escala= 1 + ruido.uniform(-0.15, 0.15)
                meio= (y1 + y2) / 2
                caixa= replace(caixa, bbox_xyxy=(x1, meio - (meio - y1) * escala, x2, meio + (y2 - meio) * escala))
            deteccoes.append(caixa)
        if ruido is not None:
            frame.heading= ruido.uniform(-2, 2) % 360
    return frames, deteccoes


def test_dois_postes_em_fila_dao_dois_elementos_no_sitio_certo():
    postes= [(1.5, 30.0), (1.5, 42.0)]
    frames, deteccoes= _video(postes)
    elementos= [e for e in locate(frames, deteccoes, MUNICIPIO, CLASSES) if e.category == "iluminacao"]
    assert len(elementos) == 2
    x0, y0= _origem()
    obtidas= sorted(PARA_METROS.transform(e.lon, e.lat) for e in elementos)
    for (x, y), (px, py) in zip(sorted(obtidas, key=lambda p: p[1]), postes, strict=True):
        assert math.hypot(x - (x0 + px), y - (y0 + py)) < 1.5


def test_um_poste_nao_se_parte_em_varios():
    frames, deteccoes= _video([(2.0, 30.0)])
    elementos= locate(frames, deteccoes, MUNICIPIO, CLASSES)
    assert len(elementos) == 1
    assert len(elementos[0].observations) == len(deteccoes)


def test_intervalo_grande_parte_o_trilho():
    x0, y0= _origem()
    a= _frame(0, x0, y0, 0)
    b= _frame(1, x0, y0 + 0.5, 10)
    caixa= (500, 400, 530, 900)
    observacoes= [
        _observe(Detection(a.id, "iluminacao", "poste_luz", caixa, 0.9, False), a),
        _observe(Detection(b.id, "iluminacao", "poste_luz", caixa, 0.9, False), b),
    ]
    assert trilhos(observacoes) == [[0], [1]]
    b.capturada_em= INICIO + timedelta(seconds=0.5)
    assert trilhos(observacoes) == [[0, 1]]


def test_fotografias_nao_usam_o_seguimento(monkeypatch):
    frames, deteccoes= _video([(2.0, 30.0)])
    for frame in frames:
        frame.fonte= "upload"
    deteccoes= [replace(d, image_id=d.image_id.replace("video:", "upload:", 1)) for d in deteccoes]

    def proibido(_):
        raise AssertionError("o seguimento só serve para vídeo")

    monkeypatch.setattr(L, "trilhos", proibido)
    assert locate(frames, deteccoes, MUNICIPIO, CLASSES)


def test_postes_em_fila_com_ruido_continuam_separados():
    postes= [(1.5, 30.0), (1.5, 42.0)]
    frames, deteccoes= _video(postes, ruido=random.Random(7))
    elementos= locate(frames, deteccoes, MUNICIPIO, CLASSES)
    assert len(elementos) == 2
    x0, y0= _origem()
    obtidas= sorted((PARA_METROS.transform(e.lon, e.lat) for e in elementos), key=lambda p: p[1])
    for (x, y), (px, py) in zip(obtidas, postes, strict=True):
        assert math.hypot(x - (x0 + px), y - (y0 + py)) < 3
