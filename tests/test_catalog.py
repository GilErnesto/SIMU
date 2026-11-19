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
    Observacao,
    element_confidence,
    ensure_schema,
    known_image_ids,
    write_catalog,
)
from pipeline.config import calibrar_confianca, load_classes
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
    luz= CLASSES.categorias["iluminacao"]
    media= (calibrar_confianca(luz, 0.8) + calibrar_confianca(luz, 0.6)) / 2
    assert linhas[0].confianca == pytest.approx(media * (1 - 0.25**2))
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
def test_elementos_proximos_da_mesma_gravacao_nao_se_juntam(sessao):
    a, b= _registo("t-g"), _registo("t-h")
    write_catalog(
        sessao, CLASSES, [a, b],
        [_elemento(a, -8.65, 40.64, 0.8), _elemento(b, -8.65002, 40.64001, 0.8)],
    )
    assert sessao.query(Elemento).filter(Elemento.classe == "candeeiro").count() == 2


@precisa_bd
def test_observacao_guarda_confianca_calibrada_so_na_iluminacao(sessao):
    a= _registo("t-e")
    luz= _elemento(a, -8.65, 40.64, 0.8)
    sinal= Element(
        "sinal", "stop", -8.66, 40.64, False, "monocular",
        [Observation(Detection(a.id, "sinal", "stop", (1, 2, 3, 4), 0.8, False), a, 10.0)],
    )
    write_catalog(sessao, CLASSES, [a], [luz, sinal])
    confianca_luz= sessao.query(Observacao).filter(Observacao.classe == "candeeiro").one().confianca
    confianca_sinal= sessao.query(Observacao).filter(Observacao.classe == "stop").one().confianca
    assert confianca_luz == pytest.approx(0.98 + 0.01 / 3)
    assert confianca_sinal == pytest.approx(0.8)


@precisa_bd
def test_exportacao(sessao):
    a= _registo("t-e")
    write_catalog(sessao, CLASSES, [a], [_elemento(a, -8.65, 40.64, 0.8)])
    geojson= to_geojson(sessao)
    assert geojson["type"] == "FeatureCollection"
    assert any(f["properties"]["atribuicao"] for f in geojson["features"])
    assert "fotografo" in to_csv(sessao)


def _registo_sem_gps(identificador):
    return ImageRecord(
        "upload", identificador, "Utilizador", "Dados do utilizador", "",
        None, None, None, None, "perspective", "u",
        width=1000, height=800, caminho_anon=f"data/anon/{identificador}.jpg",
    )


def _elemento_sem_posicao(registo, classe= "stop"):
    deteccao= Detection(registo.id, "sinal", classe, (1, 2, 30, 40), 0.7, False)
    return Element("sinal", classe, None, None, False, "sem_posicao", [Observation(deteccao, registo, None)])


@precisa_bd
def test_elementos_sem_posicao_ficam_separados_e_sem_geometria(sessao):
    a= _registo_sem_gps("t-gps-a")
    write_catalog(
        sessao, CLASSES, [a],
        [_elemento_sem_posicao(a), _elemento_sem_posicao(a)],
    )
    linhas= sessao.query(Elemento).filter(Elemento.metodo_geo == "sem_posicao").all()
    assert len(linhas) == 2
    assert all(linha.geom is None for linha in linhas)
    assert all(linha.observacoes[0].bearing is None for linha in linhas)
    assert all(linha.n_observacoes == 1 for linha in linhas)


@precisa_bd
def test_exportacao_com_elementos_sem_posicao(sessao):
    a= _registo_sem_gps("t-gps-b")
    write_catalog(sessao, CLASSES, [a], [_elemento_sem_posicao(a, "perigo")])
    features= [f for f in to_geojson(sessao)["features"] if f["properties"]["metodo_geo"] == "sem_posicao"]
    assert features
    assert all(f["geometry"] is None for f in features)
    csv_texto= to_csv(sessao)
    assert "sem_posicao" in csv_texto


@precisa_bd
def test_imagem_sem_gps_nao_tem_geometria(sessao):
    from pipeline.catalog.write import Imagem

    a= _registo_sem_gps("t-gps-c")
    write_catalog(sessao, CLASSES, [a], [_elemento_sem_posicao(a)])
    imagem= sessao.query(Imagem).filter(Imagem.id_fonte == "t-gps-c").one()
    assert imagem.geom is None
    assert imagem.heading is None


@precisa_bd
def test_migracao_torna_o_bearing_opcional_numa_base_antiga():
    from sqlalchemy import text

    engine= create_engine(URL_BD)
    ensure_schema(engine)
    consulta= text(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_name = 'observacao' AND column_name = 'bearing'"
    )
    with engine.begin() as conexao:
        conexao.execute(text("ALTER TABLE observacao ALTER COLUMN bearing SET NOT NULL"))
        assert conexao.execute(consulta).scalar() == "NO"
    ensure_schema(engine)
    with engine.connect() as conexao:
        assert conexao.execute(consulta).scalar() == "YES"
    ensure_schema(engine)


def test_feature_sem_geometria_nao_rebenta():
    elemento= SimpleNamespace(
        id=2, categoria="sinal", classe="stop", geom=None, confianca=0.5, obstruido=False,
        estado="auto", metodo_geo="sem_posicao", n_observacoes=1, observacoes=[],
    )
    feature= to_feature(elemento)
    assert feature["geometry"] is None
    assert feature["properties"]["metodo_geo"] == "sem_posicao"
