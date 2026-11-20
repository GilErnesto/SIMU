import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.deps import get_classes, get_engine, get_municipio, get_session
from backend.main import app
from pipeline.catalog.write import Correcao, Elemento, ensure_schema, write_catalog
from pipeline.config import load_classes
from pipeline.models import Detection, Element, ImageRecord, Observation

RAIZ= Path(__file__).parents[1]
CLASSES= load_classes(RAIZ / "config" / "classes.yaml")
URL_BD= os.environ.get("TEST_DATABASE_URL")
precisa_bd= pytest.mark.skipif(not URL_BD, reason="TEST_DATABASE_URL não definido")
LON, LAT= -8.6500, 40.6400


@pytest.fixture(autouse=True)
def ambiente(monkeypatch, tmp_path):
    monkeypatch.setenv("MUNICIPIO_YAML", str(RAIZ / "config" / "municipio.yaml"))
    monkeypatch.setenv("ANON_DIR", str(tmp_path / "anon"))
    get_municipio.cache_clear()
    get_classes.cache_clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def sessao():
    engine= create_engine(URL_BD)
    ensure_schema(engine)
    with engine.connect() as ligacao:
        transacao= ligacao.begin()
        with Session(ligacao, join_transaction_mode="create_savepoint") as s:
            app.dependency_overrides[get_session]= lambda: s
            yield s
        transacao.rollback()


@pytest.fixture
def cliente():
    return TestClient(app)


def _registo(identificador, caminho_anon="data/anon/a.jpg"):
    return ImageRecord(
        "mapillary", identificador, "fotografo", "CC BY-SA 4.0", f"http://x/{identificador}",
        datetime(2026, 1, 1, tzinfo=UTC), LON, LAT, 0.0, "perspective", "u",
        width=1000, height=800, caminho_anon=caminho_anon,
    )


def _criar(
    sessao,
    categoria="iluminacao",
    classe="candeeiro",
    lon=LON,
    lat=LAT,
    identificador="b-1",
    observacoes=1,
    confianca=0.8,
):
    registo= _registo(identificador)
    deteccao= Detection(registo.id, categoria, classe, (1, 2, 3, 4), confianca, False)
    elemento= Element(
        categoria,
        classe,
        lon,
        lat,
        False,
        "monocular",
        [Observation(deteccao, registo, 10.0) for _ in range(observacoes)],
    )
    write_catalog(sessao, CLASSES, [registo], [elemento])
    return sessao.scalars(select(Elemento).order_by(Elemento.id.desc())).first().id


def _criar_sem_posicao(sessao, identificador="b-sp", classe="stop"):
    registo= ImageRecord(
        "upload", identificador, "Utilizador", "Dados do utilizador", "",
        None, None, None, None, "perspective", "u",
        width=1000, height=800, caminho_anon="data/anon/sp.jpg",
    )
    deteccao= Detection(registo.id, "sinal", classe, (1, 2, 30, 40), 0.7, False)
    elemento= Element("sinal", classe, None, None, False, "sem_posicao", [Observation(deteccao, registo, None)])
    write_catalog(sessao, CLASSES, [registo], [elemento])
    return sessao.scalars(select(Elemento).order_by(Elemento.id.desc())).first().id


@precisa_bd
def test_listar_inclui_elementos_sem_posicao_com_geometria_nula(cliente, sessao):
    _criar(sessao, "iluminacao", "candeeiro", identificador="b-1")
    sem= _criar_sem_posicao(sessao)
    features= cliente.get("/elementos").json()["features"]
    por_id= {f["properties"]["id"]: f for f in features}
    assert por_id[sem]["geometry"] is None
    assert por_id[sem]["properties"]["metodo_geo"] == "sem_posicao"
    caixa= f"{LON - 0.01},{LAT - 0.01},{LON + 0.01},{LAT + 0.01}"
    assert sem not in {f["properties"]["id"] for f in cliente.get(f"/elementos?bbox={caixa}").json()["features"]}


@precisa_bd
def test_detalhe_de_elemento_sem_posicao(cliente, sessao):
    sem= _criar_sem_posicao(sessao)
    dados= cliente.get(f"/elementos/{sem}").json()
    assert dados["geometry"] is None
    assert dados["properties"]["observacoes"][0]["bearing"] is None


@precisa_bd
def test_tecnico_indica_a_posicao_de_um_elemento_sem_posicao(cliente, sessao):
    sem= _criar_sem_posicao(sessao)
    resposta= cliente.patch(f"/elementos/{sem}", json={"lon": -8.651, "lat": 40.641, "autor": "Ana"})
    assert resposta.status_code == 200
    dados= cliente.get(f"/elementos/{sem}").json()
    assert dados["geometry"]["coordinates"] == [-8.651, 40.641]
    assert dados["properties"]["metodo_geo"] == "manual"
    assert dados["properties"]["estado"] == "corrigido"
    consulta= select(Correcao).where(Correcao.elemento_id == sem, Correcao.campo == "posicao")
    correcao= sessao.scalars(consulta).one()
    assert correcao.valor_antigo == ""
    assert correcao.valor_novo == "-8.651,40.641"


@precisa_bd
def test_corrigir_so_o_estado_de_um_elemento_sem_posicao(cliente, sessao):
    sem= _criar_sem_posicao(sessao)
    resposta= cliente.patch(f"/elementos/{sem}", json={"estado": "validado", "autor": "Ana"})
    assert resposta.status_code == 200
    assert cliente.get(f"/elementos/{sem}").json()["geometry"] is None


def test_config_expoe_taxonomia_e_municipio(cliente):
    resposta= cliente.get("/config")
    assert resposta.status_code == 200
    dados= resposta.json()
    assert dados["categorias"]["sinal"]["rotulo"] == "Sinais"
    assert dados["categorias"]["sinal"]["classes"][0] == {"id": "perigo", "rotulo": "Sinais de perigo"}
    assert len(dados["bbox"]) == 4
    assert "rejeitado" in dados["estados"]


def test_bbox_invalida(cliente):
    assert cliente.get("/elementos?bbox=1,2,3").status_code == 422
    assert cliente.get("/elementos?bbox=5,5,1,1").status_code == 422


def test_categoria_desconhecida(cliente):
    assert cliente.get("/elementos?categoria=banco").status_code == 422


@precisa_bd
def test_listar_com_filtros(cliente, sessao):
    _criar(sessao, "iluminacao", "candeeiro", identificador="b-1")
    _criar(sessao, "sinal", "stop", LON + 0.001, LAT, identificador="b-2")
    caixa= f"{LON - 0.01},{LAT - 0.01},{LON + 0.01},{LAT + 0.01}"
    todos= cliente.get(f"/elementos?bbox={caixa}").json()
    assert todos["type"] == "FeatureCollection"
    assert len(todos["features"]) == 2
    luz= cliente.get(f"/elementos?bbox={caixa}&categoria=iluminacao").json()
    assert [f["properties"]["classe"] for f in luz["features"]] == ["candeeiro"]
    assert cliente.get("/elementos?bbox=10,10,11,11").json()["features"] == []
    assert cliente.get(f"/elementos?bbox={caixa}&estado=validado").json()["features"] == []


@precisa_bd
def test_minimo_de_observacoes(cliente, sessao):
    caixa= f"{LON - 0.01},{LAT - 0.01},{LON + 0.01},{LAT + 0.01}"
    _criar(sessao, "iluminacao", "candeeiro", identificador="b-1")
    _criar(sessao, "sinal", "stop", identificador="b-2", observacoes=3)
    dois= cliente.get(f"/elementos?bbox={caixa}&min_observacoes=2").json()["features"]
    assert [f["properties"]["classe"] for f in dois] == ["stop"]
    assert dois[0]["properties"]["n_observacoes"] == 3
    todos= cliente.get(f"/elementos?bbox={caixa}&min_observacoes=1").json()["features"]
    assert len(todos) == 2
    assert cliente.get(f"/elementos?bbox={caixa}&min_observacoes=4").json()["features"] == []


@precisa_bd
def test_confianca_minima(cliente, sessao):
    caixa= f"{LON - 0.01},{LAT - 0.01},{LON + 0.01},{LAT + 0.01}"
    _criar(sessao, "iluminacao", "candeeiro", identificador="b-1", confianca=0.5)
    _criar(sessao, "sinal", "stop", identificador="b-2", observacoes=3, confianca=0.9)
    alta= cliente.get(f"/elementos?bbox={caixa}&min_confianca=0.8").json()["features"]
    assert [f["properties"]["classe"] for f in alta] == ["stop"]
    media= cliente.get(f"/elementos?bbox={caixa}&min_confianca=0.3").json()["features"]
    assert len(media) == 2


def test_filtros_numericos_invalidos(cliente):
    assert cliente.get("/elementos?min_observacoes=0").status_code == 422
    assert cliente.get("/elementos?min_confianca=2").status_code == 422
    assert cliente.get("/export.geojson?min_confianca=-1").status_code == 422
    assert cliente.get("/export.geojson?categoria=banco").status_code == 422


@precisa_bd
def test_exportacoes_respeitam_filtros(cliente, sessao):
    _criar(sessao, "iluminacao", "candeeiro", identificador="b-1", confianca=0.5)
    _criar(sessao, "sinal", "stop", identificador="b-2", observacoes=3, confianca=0.9)
    geojson= cliente.get("/export.geojson?min_observacoes=2").json()
    assert [f["properties"]["classe"] for f in geojson["features"]] == ["stop"]
    csv= cliente.get("/export.csv?categoria=sinal&min_confianca=0.8").text
    assert "stop" in csv
    assert "candeeiro" not in csv


@precisa_bd
def test_detalhe_com_atribuicao(cliente, sessao):
    elemento_id= _criar(sessao)
    dados= cliente.get(f"/elementos/{elemento_id}").json()["properties"]
    observacao= dados["observacoes"][0]
    assert observacao["imagem"]["autor"] == "fotografo"
    assert observacao["imagem"]["licenca"] == "CC BY-SA 4.0"
    assert observacao["imagem"]["url_origem"] == "http://x/b-1"
    assert observacao["imagem"]["url"].startswith("/imagens/")
    assert cliente.get("/elementos/999999").status_code == 404


@precisa_bd
def test_corrigir_classe_regista_correcao_e_marca_corrigido(cliente, sessao):
    elemento_id= _criar(sessao, "sinal", "stop")
    resposta= cliente.patch(
        f"/elementos/{elemento_id}", json={"autor": "tecnico", "classe": "cedencia"}
    )
    assert resposta.status_code == 200
    propriedades= resposta.json()["properties"]
    assert propriedades["classe"] == "cedencia"
    assert propriedades["estado"] == "corrigido"
    campos= {c.campo: (c.valor_antigo, c.valor_novo, c.autor) for c in sessao.scalars(select(Correcao))}
    assert campos["classe"] == ("stop", "cedencia", "tecnico")
    assert campos["estado"] == ("auto", "corrigido", "tecnico")


@precisa_bd
def test_corrigir_posicao(cliente, sessao):
    elemento_id= _criar(sessao)
    resposta= cliente.patch(
        f"/elementos/{elemento_id}", json={"autor": "t", "lon": -8.651, "lat": 40.641}
    )
    assert resposta.json()["geometry"]["coordinates"] == [-8.651, 40.641]
    assert any(c.campo == "posicao" for c in sessao.scalars(select(Correcao)))


@precisa_bd
def test_rejeitar_nao_apaga(cliente, sessao):
    elemento_id= _criar(sessao)
    resposta= cliente.patch(f"/elementos/{elemento_id}", json={"autor": "t", "estado": "rejeitado"})
    assert resposta.json()["properties"]["estado"] == "rejeitado"
    assert cliente.get(f"/elementos/{elemento_id}").status_code == 200
    assert len(cliente.get("/elementos?estado=rejeitado").json()["features"]) == 1


@precisa_bd
def test_sem_alteracao_nao_cria_correcao(cliente, sessao):
    elemento_id= _criar(sessao)
    cliente.patch(f"/elementos/{elemento_id}", json={"autor": "t", "classe": "candeeiro"})
    assert list(sessao.scalars(select(Correcao))) == []


@precisa_bd
@pytest.mark.parametrize(
    "corpo",
    [
        {"autor": "t", "classe": "stop"},
        {"autor": "t", "lon": -8.6},
        {"autor": "t"},
        {"autor": "", "estado": "validado"},
        {"autor": "t", "estado": "apagado"},
        {"autor": "t", "lon": 500, "lat": 40},
    ],
)
def test_correcao_invalida(cliente, sessao, corpo):
    elemento_id= _criar(sessao)
    assert cliente.patch(f"/elementos/{elemento_id}", json=corpo).status_code == 422
    assert list(sessao.scalars(select(Correcao))) == []


@precisa_bd
def test_imagem_so_da_pasta_anonimizada(cliente, sessao, tmp_path):
    elemento_id= _criar(sessao)
    url= cliente.get(f"/elementos/{elemento_id}").json()["properties"]["observacoes"][0]["imagem"]["url"]
    assert cliente.get(url).status_code == 404
    anon= tmp_path / "anon"
    anon.mkdir()
    (anon / "a.jpg").write_bytes(b"jpeg")
    resposta= cliente.get(url)
    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == "image/jpeg"


@precisa_bd
def test_imagem_nao_sai_da_pasta(cliente, sessao, tmp_path):
    registo= _registo("b-9", caminho_anon="../segredo.jpg")
    deteccao= Detection(registo.id, "iluminacao", "candeeiro", (1, 2, 3, 4), 0.8, False)
    elemento= Element("iluminacao", "candeeiro", LON, LAT, False, "monocular", [Observation(deteccao, registo, 1.0)])
    write_catalog(sessao, CLASSES, [registo], [elemento])
    (tmp_path / "segredo.jpg").write_bytes(b"x")
    (tmp_path / "anon").mkdir()
    imagem_id= cliente.get("/elementos").json()["features"][0]
    url= cliente.get(f"/elementos/{imagem_id['properties']['id']}").json()["properties"]["observacoes"][0]["imagem"]["url"]
    assert cliente.get(url).status_code == 404


@precisa_bd
def test_exportacoes(cliente, sessao):
    _criar(sessao)
    geojson= cliente.get("/export.geojson")
    assert geojson.headers["content-type"].startswith("application/geo+json")
    assert geojson.json()["features"][0]["properties"]["atribuicao"][0]["autor"] == "fotografo"
    csv= cliente.get("/export.csv")
    assert csv.headers["content-type"].startswith("text/csv")
    assert "fotografo" in csv.text


@precisa_bd
def test_arranque_cria_o_esquema(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL_BD)
    get_engine.cache_clear()
    try:
        with TestClient(app) as cliente:
            resposta= cliente.get("/elementos")
        assert resposta.status_code == 200
        assert resposta.json()["type"] == "FeatureCollection"
    finally:
        get_engine.cache_clear()
