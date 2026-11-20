import io

import cv2
import numpy as np

from pipeline.bancada import (
    amostrar,
    elementos_geojson,
    imagens_do_mapillary,
    imagens_geojson,
    so_estas,
)
from pipeline.catalog.write import element_confidence
from pipeline.errors import ErroPipeline
from pipeline.models import Detection, Element, ImageRecord, Observation


def _imagem(id_fonte):
    return ImageRecord("mapillary", id_fonte, "a", "CC BY-SA 4.0", "u", None, -8.66, 40.63, 0.0, "perspective", "")


def test_elementos_geojson_usa_a_formula_de_confianca_do_catalogo():
    imagem= _imagem("1")
    observacoes= [
        Observation(Detection(imagem.id, "sinal", "stop", (0, 0, 1, 1), conf, False), imagem, 10.0)
        for conf in (0.6, 0.8)
    ]
    colecao= elementos_geojson([Element("sinal", "stop", -8.66, 40.63, False, "triangulacao", observacoes)])
    propriedades= colecao["features"][0]["properties"]
    assert propriedades["categoria"] == "sinal"
    assert propriedades["n_observacoes"] == 2
    assert propriedades["confianca"] == element_confidence(0.7, 2)


def test_so_estas_filtra_pelos_ids_pedidos_e_ordena():
    registos= [_imagem(f"{n:03d}") for n in range(10)]
    assert [r.id_fonte for r in so_estas(registos, {"007", "002", "999"})] == ["002", "007"]


def test_amostrar_e_estavel_quando_a_listagem_muda():
    registos= [_imagem(f"{n:03d}") for n in range(100)]
    escolhidas= {r.id_fonte for r in amostrar(registos, 20)}
    assert len(escolhidas) == 20
    assert {r.id_fonte for r in amostrar(list(reversed(registos)), 20)} == escolhidas
    fora= next(r for r in registos if r.id_fonte not in escolhidas)
    assert {r.id_fonte for r in amostrar([r for r in registos if r is not fora], 20)} == escolhidas
    com_nova= {r.id_fonte for r in amostrar([*registos, _imagem("000a")], 20)}
    assert len(com_nova & escolhidas) >= 19
    assert len(amostrar(registos[:10], None)) == 10
    assert len(amostrar(registos[:10], 50)) == 10


def test_imagens_do_mapillary_grava_so_anonimizadas(tmp_path):
    def baixar(registo):
        if registo.id_fonte == "falha":
            raise ErroPipeline("sem rede")
        return np.full((20, 30, 3), 255, np.uint8)

    carregamentos= []

    def carregar():
        carregamentos.append(1)
        return lambda imagem: np.zeros_like(imagem)

    prontas= imagens_do_mapillary([_imagem("ok"), _imagem("falha")], tmp_path, carregar, baixar, io.StringIO())
    assert [r.id_fonte for r in prontas] == ["ok"]
    assert cv2.imread(prontas[0].caminho_anon).max() == 0
    assert imagens_do_mapillary([_imagem("ok")], tmp_path, carregar, baixar, io.StringIO())[0].id_fonte == "ok"
    assert len(carregamentos) == 1


def test_imagens_geojson():
    colecao= imagens_geojson([_imagem("1"), _imagem("2")])
    assert [f["properties"]["id_fonte"] for f in colecao["features"]] == ["1", "2"]
