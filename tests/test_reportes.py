import os
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.deps import get_classes, get_municipio, get_session
from backend.main import app
from pipeline.catalog import reportes
from pipeline.catalog.write import Reporte, ensure_schema
from pipeline.config import load_classes
from pipeline.models import Detection

RAIZ= Path(__file__).parents[1]
CLASSES= load_classes(RAIZ / "config" / "classes.yaml")
URL_BD= os.environ.get("TEST_DATABASE_URL")
precisa_bd= pytest.mark.skipif(not URL_BD, reason="TEST_DATABASE_URL não definido")
CIDADAO= "cidadao-de-teste-1"
LON, LAT= -8.6500, 40.6400


def _rascunho(**campos):
    base= {"estado": "rascunho", "estado_foto": "pronta", "caixas": [{"categoria": "sinal", "classe": "stop", "caixa": [1, 2, 3, 4]}]}
    return SimpleNamespace(**{**base, **campos})


def test_cada_categoria_tem_problemas_para_reportar():
    for categoria in CLASSES.categorias.values():
        assert "outro" in categoria.problemas
    assert "torto" in CLASSES.categorias["sinal"].problemas


def test_escolher_uma_caixa_detetada():
    assert reportes.validar_escolha(CLASSES, _rascunho(), "torto", 0, None, None) == ("sinal", "stop", [1, 2, 3, 4])


def test_escolher_o_tipo_quando_o_objeto_nao_foi_detetado():
    assert reportes.validar_escolha(CLASSES, _rascunho(caixas=[]), "cheio", None, None, "residuos") == ("residuos", None, None)


@pytest.mark.parametrize(
    ("reporte", "problema", "indice", "categoria", "mensagem"),
    [
        (_rascunho(), "torto", 5, None, "objetos encontrados"),
        (_rascunho(estado_foto="na_fila"), "torto", 0, None, "objetos encontrados"),
        (_rascunho(), "cheio", 0, None, "Problema inválido"),
        (_rascunho(caixas=[]), "torto", None, "nao_existe", "sinal, iluminação ou contentor"),
        (_rascunho(estado="aberto"), "torto", 0, None, "já foi enviado"),
    ],
)
def test_escolhas_invalidas(reporte, problema, indice, categoria, mensagem):
    with pytest.raises(reportes.ErroReporte, match=mensagem):
        reportes.validar_escolha(CLASSES, reporte, problema, indice, None, categoria)


def test_titulo_do_reporte():
    assert reportes.descrever(CLASSES, SimpleNamespace(categoria="sinal", classe="stop", problema="torto")) == (
        "Sinal torto ou caído (Cedência de passagem (STOP))"
    )
    assert reportes.descrever(CLASSES, SimpleNamespace(categoria="residuos", classe=None, problema="cheio")) == (
        "Contentor cheio (Resíduos)"
    )


@pytest.fixture
def ambiente(monkeypatch, tmp_path):
    monkeypatch.setenv("MUNICIPIO_YAML", str(RAIZ / "config" / "municipio.yaml"))
    monkeypatch.setenv("ANON_DIR", str(tmp_path / "anon"))
    monkeypatch.setenv("RAW_DIR", str(tmp_path / "raw"))
    get_municipio.cache_clear()
    get_classes.cache_clear()
    yield tmp_path
    app.dependency_overrides.clear()


@pytest.fixture
def sessao(ambiente):
    engine= create_engine(URL_BD)
    ensure_schema(engine)
    with engine.connect() as ligacao:
        transacao= ligacao.begin()
        with Session(ligacao, join_transaction_mode="create_savepoint") as s:
            app.dependency_overrides[get_session]= lambda: s
            yield s
        transacao.rollback()


class _Detetor:
    def detect(self, image_id, image):
        return [Detection(image_id, "sinal", "stop", (10, 10, 40, 40), 0.9, False)]


def _foto() -> bytes:
    imagem= np.full((60, 80, 3), 120, np.uint8)
    return cv2.imencode(".jpg", imagem)[1].tobytes()


def _reporte_pronto(cliente, sessao, ambiente, lon=LON, lat=LAT) -> str:
    """Citizen sends a photo, the worker (fake detector) finds one STOP sign in it."""
    resposta= cliente.post(
        "/reportes", files={"foto": ("f.jpg", _foto(), "image/jpeg")}, data={"cidadao": CIDADAO, "lon": lon, "lat": lat}
    )
    assert resposta.status_code == 201
    token= resposta.json()["token"]
    reporte= reportes.reclamar_foto(sessao)
    assert reporte.token == token
    assert reportes.processar_foto(sessao, reporte, lambda img: img, _Detetor(), ambiente / "raw", ambiente / "anon")
    return token


@precisa_bd
def test_fluxo_completo_do_cidadao_ao_tecnico(sessao, ambiente):
    from tests.test_backend import _criar

    elemento_id= _criar(sessao, categoria="sinal", classe="stop", lon=LON + 0.00003, lat=LAT)
    cliente= TestClient(app)
    token= _reporte_pronto(cliente, sessao, ambiente)
    assert not reportes.caminho_raw(ambiente / "raw", token).exists()
    dados= cliente.get(f"/reportes/{token}").json()
    assert dados["estado"] == "rascunho" and dados["caixas"][0]["classe"] == "stop"
    assert cliente.get(f"/reportes/{token}/foto").status_code == 200

    enviado= cliente.post(f"/reportes/{token}/enviar", json={"indice": 0, "problema": "torto", "descricao": "Inclinado"})
    assert enviado.status_code == 200
    assert enviado.json()["elemento_id"] == elemento_id
    mapa= cliente.get("/elementos", params={"com_reportes": True}).json()["features"]
    assert [f["properties"]["reportes_abertos"] for f in mapa] == [1]

    assert cliente.patch(f"/reportes/{token}", json={"autor": "Ana", "estado": "resolvido", "nota": "Endireitado"}).status_code == 200
    notificacoes= cliente.get(f"/cidadaos/{CIDADAO}/notificacoes").json()
    assert notificacoes["nao_lidas"] == 1
    assert "foi resolvido" in notificacoes["notificacoes"][0]["texto"]
    assert "Endireitado" in notificacoes["notificacoes"][0]["texto"]
    cliente.post(f"/cidadaos/{CIDADAO}/notificacoes/lidas")
    assert cliente.get(f"/cidadaos/{CIDADAO}/notificacoes").json()["nao_lidas"] == 0

    assert cliente.get("/reportes").json()["features"] == []
    assert [f["properties"]["token"] for f in cliente.get("/reportes", params={"estado": "arquivo"}).json()["features"]] == [token]
    historico= [e["estado"] for e in cliente.get(f"/reportes/{token}").json()["eventos"]]
    assert historico == ["rascunho", "aberto", "resolvido"]
    assert cliente.get("/reportes.csv").text.count("Endireitado") == 1
    assert cliente.get("/elementos", params={"com_reportes": True}).json()["features"] == []


@precisa_bd
def test_tecnico_nao_mexe_num_rascunho_nem_inventa_estados(sessao, ambiente):
    cliente= TestClient(app)
    token= _reporte_pronto(cliente, sessao, ambiente)
    assert cliente.patch(f"/reportes/{token}", json={"autor": "Ana", "estado": "resolvido"}).status_code == 409
    assert cliente.patch(f"/reportes/{token}", json={"autor": "Ana", "estado": "apagado"}).status_code == 422


@precisa_bd
def test_reporte_sem_localizacao_nao_se_liga_a_nenhum_elemento(sessao, ambiente):
    cliente= TestClient(app)
    resposta= cliente.post("/reportes", files={"foto": ("f.jpg", _foto(), "image/jpeg")}, data={"cidadao": CIDADAO})
    token= resposta.json()["token"]
    reportes.processar_foto(sessao, reportes.reclamar_foto(sessao), lambda img: img, _Detetor(), ambiente / "raw", ambiente / "anon")
    dados= cliente.post(f"/reportes/{token}/enviar", json={"categoria": "residuos", "problema": "cheio"}).json()
    assert dados["elemento_id"] is None and dados["lat"] is None
    assert sessao.scalar(select(Reporte.estado).where(Reporte.token == token)) == "aberto"


@precisa_bd
def test_pedidos_invalidos_do_cidadao(sessao, ambiente):
    cliente= TestClient(app)
    assert cliente.post("/reportes", files={"foto": ("f.jpg", b"nao e imagem", "image/jpeg")}, data={"cidadao": CIDADAO}).status_code == 400
    assert cliente.post("/reportes", files={"foto": ("f.jpg", _foto(), "image/jpeg")}, data={"cidadao": "x"}).status_code == 422
    assert cliente.get("/reportes/nao-existe").status_code == 404
    assert cliente.get("/cidadaos/x/notificacoes").status_code == 422


@precisa_bd
def test_mesmo_problema_no_mesmo_elemento_confirma_o_reporte_aberto(sessao, ambiente):
    from tests.test_backend import _criar

    elemento_id= _criar(sessao, categoria="sinal", classe="stop", lon=LON + 0.00003, lat=LAT)
    cliente= TestClient(app)
    primeiro= _reporte_pronto(cliente, sessao, ambiente)
    cliente.post(f"/reportes/{primeiro}/enviar", json={"indice": 0, "problema": "torto"})
    segundo= _reporte_pronto(cliente, sessao, ambiente)
    dados= cliente.post(f"/reportes/{segundo}/enviar", json={"indice": 0, "problema": "torto"}).json()
    assert dados["principal"] == primeiro
    outro= _reporte_pronto(cliente, sessao, ambiente)
    assert cliente.post(f"/reportes/{outro}/enviar", json={"indice": 0, "problema": "vandalizado"}).json()["principal"] is None

    fila= cliente.get("/reportes").json()["features"]
    assert sorted(f["properties"]["token"] for f in fila) == sorted([primeiro, outro])
    assert next(f for f in fila if f["properties"]["token"] == primeiro)["properties"]["confirmacoes"] == 1
    mapa= cliente.get("/elementos", params={"com_reportes": True}).json()["features"]
    assert mapa[0]["properties"]["reportes_abertos"] == 2

    detalhe= cliente.get(f"/elementos/{elemento_id}").json()["properties"]
    assert [o.get("cidadao", False) for o in detalhe["observacoes"]] == [True, True, True, False]
    assert detalhe["n_fotos_cidadao"] == 3

    # Resolving it through the confirmation's token resolves both and tells both citizens.
    assert cliente.patch(f"/reportes/{segundo}", json={"autor": "Ana", "estado": "resolvido"}).status_code == 200
    assert cliente.get(f"/reportes/{primeiro}").json()["estado"] == "resolvido"
    assert cliente.get(f"/reportes/{segundo}").json()["estado"] == "resolvido"
    assert cliente.get(f"/cidadaos/{CIDADAO}/notificacoes").json()["nao_lidas"] == 2


@precisa_bd
def test_reportes_de_uma_analise_incluem_os_soltos_na_sua_area(sessao, ambiente):
    from pipeline.catalog import analises
    from pipeline.catalog.write import Elemento
    from tests.test_backend import _criar

    elemento_id= _criar(sessao, categoria="sinal", classe="stop")
    analise= analises.criar(sessao, "Zona", estado="concluida")
    sessao.get(Elemento, elemento_id).analise_id= analise.id
    sessao.flush()
    cliente= TestClient(app)
    perto= _reporte_pronto(cliente, sessao, ambiente, lon=LON + 0.0002, lat=LAT)
    cliente.post(f"/reportes/{perto}/enviar", json={"categoria": "residuos", "problema": "cheio"})
    longe= _reporte_pronto(cliente, sessao, ambiente, lon=LON + 0.05, lat=LAT)
    cliente.post(f"/reportes/{longe}/enviar", json={"categoria": "residuos", "problema": "cheio"})
    tokens= [f["properties"]["token"] for f in cliente.get("/reportes", params={"analise": analise.token}).json()["features"]]
    assert tokens == [perto]
    exportado= cliente.get("/reportes.geojson").json()
    assert {f["properties"]["token"] for f in exportado["features"]} == {perto, longe}
    assert exportado["features"][0]["properties"]["eventos"]
