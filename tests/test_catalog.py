import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from geoalchemy2 import WKTElement
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pipeline.catalog.export import to_csv, to_feature, to_geojson
from pipeline.catalog.write import (
    Elemento,
    element_confidence,
    ensure_schema,
    known_image_ids,
    write_catalog,
)
from pipeline.config import load_classes
from pipeline.models import Detection, Element, ImageRecord, Observation

CLASSES= load_classes(Path(__file__).parents[1] / "config" / "classes.yaml")
URL_BD= os.environ.get("TEST_DATABASE_URL")
precisa_bd= pytest.mark.skipif(not URL_BD, reason="TEST_DATABASE_URL não definido")


def test_confianca_sobe_com_observacoes():
    assert element_confidence(0.8, 1) == pytest.approx(0.6)
    assert element_confidence(0.8, 2) > element_confidence(0.8, 1)
    assert element_confidence(0.8, 5) < 0.8


def test_feature_com_atribuicao():
    imagem= SimpleNamespace(
        autor="fotografo", fonte="mapillary", licenca="CC BY-SA 4.0", url_origem="http://x/1"
    )
    elemento= SimpleNamespace(
        id=1,
        categoria="sinal",
        classe="stop",
        geom=WKTElement("POINT(-8.65 40.64)", srid=4326),
        confianca=0.7,
        obstruido=False,
        estado="auto",
        metodo_geo="monocular",
        n_observacoes=1,
        observacoes=[SimpleNamespace(imagem=imagem)],
    )
    feature= to_feature(elemento)
    assert feature["geometry"]["coordinates"] == [-8.65, 40.64]
    assert feature["properties"]["atribuicao"][0]["autor"] == "fotografo"
    assert feature["properties"]["atribuicao"][0]["licenca"] == "CC BY-SA 4.0"


def _registo(identificador):
    return ImageRecord(
        "mapillary", identificador, "fotografo", "CC BY-SA 4.0", f"http://x/{identificador}",
        datetime(2026, 1, 1, tzinfo=UTC), -8.65, 40.64, 0.0, "perspective", "u",
        width=1000, height=800, caminho_anon=f"data/anon/{identificador}.jpg",
    )


def _elemento(registo, lon, lat, confianca):
    deteccao= Detection(registo.id, "iluminacao", "candeeiro", (1, 2, 3, 4), confianca, False)
    return Element(
        "iluminacao", "candeeiro", lon, lat, False, "monocular",
        [Observation(deteccao, registo, 10.0)],
    )


@pytest.fixture
def sessao():
    engine= create_engine(URL_BD)
    ensure_schema(engine)
    with Session(engine) as sessao:
        sessao.begin_nested()
        yield sessao
        sessao.rollback()


@precisa_bd
def test_elemento_repetido_nao_duplica(sessao):
    a, b= _registo("t-a"), _registo("t-b")
    write_catalog(sessao, CLASSES, [a], [_elemento(a, -8.65, 40.64, 0.8)])
    write_catalog(sessao, CLASSES, [b], [_elemento(b, -8.65001, 40.64001, 0.6)])
    linhas= sessao.query(Elemento).filter(Elemento.classe == "candeeiro").all()
    assert len(linhas) == 1
    assert linhas[0].n_observacoes == 2
    assert linhas[0].confianca == pytest.approx(0.7 * (1 - 0.25**2))
    assert known_image_ids(sessao, "mapillary") >= {"t-a", "t-b"}


@precisa_bd
def test_elementos_distantes_ficam_separados(sessao):
    a, b= _registo("t-c"), _registo("t-d")
    write_catalog(
        sessao, CLASSES, [a, b],
        [_elemento(a, -8.65, 40.64, 0.8), _elemento(b, -8.66, 40.64, 0.8)],
    )
    assert sessao.query(Elemento).filter(Elemento.classe == "candeeiro").count() == 2


@precisa_bd
def test_exportacao(sessao):
    a= _registo("t-e")
    write_catalog(sessao, CLASSES, [a], [_elemento(a, -8.65, 40.64, 0.8)])
    geojson= to_geojson(sessao)
    assert geojson["type"] == "FeatureCollection"
    assert any(f["properties"]["atribuicao"] for f in geojson["features"])
    assert "fotografo" in to_csv(sessao)
