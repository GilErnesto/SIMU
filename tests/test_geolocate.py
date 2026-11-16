from pathlib import Path

import numpy as np
import pytest
from pyproj import Transformer

from pipeline.config import load_classes, load_municipio
from pipeline.geolocate.bearing import (
    horizontal_fov,
    monocular_distance,
    object_bearing,
    vertical_fov,
)
from pipeline.geolocate.dedup import cluster
from pipeline.geolocate.locate import locate
from pipeline.geolocate.triangulate import intersect
from pipeline.models import Detection, ImageRecord

CONFIG= Path(__file__).parents[1] / "config"
MUNICIPIO= load_municipio(CONFIG / "municipio.yaml")
CLASSES= load_classes(CONFIG / "classes.yaml")
PARA_GRAUS= Transformer.from_crs(MUNICIPIO.crs_metrico, "EPSG:4326", always_xy=True)
PARA_METROS= Transformer.from_crs("EPSG:4326", MUNICIPIO.crs_metrico, always_xy=True)


def test_bearing_centro_da_imagem():
    assert object_bearing(90, 500, 1000, 65) == pytest.approx(90)


def test_bearing_margem_direita():
    assert object_bearing(90, 1000, 1000, 60) == pytest.approx(120)


def test_bearing_volta_a_zero():
    assert object_bearing(350, 1000, 1000, 60) == pytest.approx(20)


def test_fov_esferico():
    assert horizontal_fov("spherical") == 360
    assert horizontal_fov("perspective") < 180
    assert vertical_fov("spherical", 4000, 2000) == 180


def test_distancia_monocular():
    distancia= monocular_distance(1.0, 100, 1000, 60)
    assert distancia == pytest.approx(1.0 / (2 * np.tan(np.radians(3))))
    assert monocular_distance(1.0, 0, 1000, 60) is None


def test_interseta_dois_raios():
    ponto= intersect((0, 0), 45, (10, 0), 315)
    assert ponto == pytest.approx((5, 5))


def test_raios_paralelos_ou_quase():
    assert intersect((0, 0), 0, (10, 0), 5) is None
    assert intersect((0, 0), 0, (10, 0), 0) is None


def test_interseta_atras_da_camara():
    assert intersect((0, 0), 225, (10, 0), 135) is None


def test_dbscan_junta_perto_e_separa_longe():
    pontos= np.array([[0, 0], [3, 0], [100, 0]])
    rotulos= cluster(pontos, 5)
    assert rotulos[0] == rotulos[1] != rotulos[2]


def _imagem(identificador, x, y, heading):
    lon, lat= PARA_GRAUS.transform(x, y)
    return ImageRecord(
        "mapillary", identificador, "autor", "CC BY-SA 4.0", "url", None, lon, lat,
        heading, "perspective", "url_imagem", width=1000, height=800,
    )


def _deteccao(imagem, classe="candeeiro", categoria="iluminacao", y1=300, y2=500):
    return Detection(imagem.id, categoria, classe, (480, y1, 520, y2), 0.9, False)


def _origem_metrica():
    return PARA_METROS.transform(*[(a + b) / 2 for a, b in zip(MUNICIPIO.bbox[:2], MUNICIPIO.bbox[2:])])


def test_triangulacao_de_duas_imagens():
    x0, y0= _origem_metrica()
    a= _imagem("a", x0, y0, 45)
    b= _imagem("b", x0 + 10, y0, 315)
    elementos= locate([a, b], [_deteccao(a), _deteccao(b)], MUNICIPIO, CLASSES)
    assert len(elementos) == 1
    elemento= elementos[0]
    assert elemento.metodo_geo == "triangulacao"
    x, y= PARA_METROS.transform(elemento.lon, elemento.lat)
    assert (x, y) == pytest.approx((x0 + 5, y0 + 5), abs=0.1)
    assert len(elemento.observations) == 2


def test_monocular_com_uma_imagem():
    x0, y0= _origem_metrica()
    a= _imagem("a", x0, y0, 0)
    elementos= locate([a], [_deteccao(a)], MUNICIPIO, CLASSES)
    assert len(elementos) == 1
    assert elementos[0].metodo_geo == "monocular"
    x, y= PARA_METROS.transform(elementos[0].lon, elementos[0].lat)
    assert x == pytest.approx(x0, abs=0.01)
    assert y > y0


def test_classes_diferentes_no_mesmo_ponto_ficam_separadas():
    x0, y0= _origem_metrica()
    a= _imagem("a", x0, y0, 0)
    detecoes= [
        _deteccao(a, "stop", "sinal", 300, 330),
        _deteccao(a, "cedencia", "sinal", 300, 330),
    ]
    elementos= locate([a], detecoes, MUNICIPIO, CLASSES)
    assert sorted(e.class_name for e in elementos) == ["cedencia", "stop"]


def test_deteccao_longe_demais_e_ignorada():
    x0, y0= _origem_metrica()
    a= _imagem("a", x0, y0, 0)
    assert locate([a], [_deteccao(a, y1=400, y2=401)], MUNICIPIO, CLASSES) == []


def _det_com(imagem, categoria, classe, confianca, y1= 300, y2= 500):
    return Detection(imagem.id, categoria, classe, (480, y1, 520, y2), confianca, False)


def _tres_imagens(x0, y0):
    return [
        _imagem("a", x0, y0, 45),
        _imagem("b", x0 + 10, y0, 315),
        _imagem("c", x0 + 5, y0 - 3, 0),
    ]


def test_classe_do_elemento_sai_da_votacao_das_imagens():
    x0, y0= _origem_metrica()
    a, b, c= _tres_imagens(x0, y0)
    detecoes= [
        _det_com(a, "sinal", "stop", 0.9),
        _det_com(b, "sinal", "stop", 0.8),
        _det_com(c, "sinal", "proibicao", 0.5),
    ]
    elementos= locate([a, b, c], detecoes, MUNICIPIO, CLASSES)
    assert len(elementos) == 1
    assert elementos[0].class_name == "stop"
    assert len(elementos[0].observations) == 3


def test_classe_geral_junta_se_a_especifica():
    x0, y0= _origem_metrica()
    a, b, _= _tres_imagens(x0, y0)
    detecoes= [_det_com(a, "sinal", "outro", 0.6), _det_com(b, "sinal", "stop", 0.9)]
    elementos= locate([a, b], detecoes, MUNICIPIO, CLASSES)
    assert [e.class_name for e in elementos] == ["stop"]
    assert len(elementos[0].observations) == 2


def test_so_classe_geral_fica_por_classificar():
    x0, y0= _origem_metrica()
    a, b, _= _tres_imagens(x0, y0)
    detecoes= [_det_com(a, "residuos", "contentor", 0.6), _det_com(b, "residuos", "contentor", 0.5)]
    elementos= locate([a, b], detecoes, MUNICIPIO, CLASSES)
    assert [e.class_name for e in elementos] == ["contentor"]


def test_dois_sinais_no_mesmo_poste_ficam_separados():
    x0, y0= _origem_metrica()
    a, b, _= _tres_imagens(x0, y0)
    detecoes= []
    for imagem in (a, b):
        detecoes.append(_det_com(imagem, "sinal", "stop", 0.9))
        detecoes.append(_det_com(imagem, "sinal", "informacao", 0.8))
    elementos= locate([a, b], detecoes, MUNICIPIO, CLASSES)
    assert sorted(e.class_name for e in elementos) == ["informacao", "stop"]
    assert all(len(e.observations) == 2 for e in elementos)


def test_classe_isolada_com_pouco_apoio_e_absorvida():
    x0, y0= _origem_metrica()
    a, b, c= _tres_imagens(x0, y0)
    d= _imagem("d", x0 + 5, y0 - 6, 0)
    detecoes= [
        _det_com(a, "sinal", "stop", 0.9),
        _det_com(b, "sinal", "stop", 0.8),
        _det_com(c, "sinal", "stop", 0.7),
        _det_com(d, "sinal", "proibicao", 0.6),
    ]
    elementos= locate([a, b, c, d], detecoes, MUNICIPIO, CLASSES)
    assert [e.class_name for e in elementos] == ["stop"]
    assert len(elementos[0].observations) == 4
