import functools
import io
import os
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.deps import get_classes, get_municipio, get_session
from backend.main import app
from pipeline import run, worker
from pipeline.catalog import analises
from pipeline.catalog.write import Imagem, ensure_schema
from pipeline.config import load_classes, load_municipio
from pipeline.ingest import mapillary
from pipeline.models import Detection, ImageRecord
from pipeline.worker import processar_analise

RAIZ= Path(__file__).parents[1]
CLASSES= load_classes(RAIZ / "config" / "classes.yaml")
MUNICIPIO= load_municipio(RAIZ / "config" / "municipio.yaml")
URL_BD= os.environ.get("TEST_DATABASE_URL")
pytestmark= pytest.mark.skipif(not URL_BD, reason="TEST_DATABASE_URL não definido")
BBOX= [-8.65, 40.64, -8.645, 40.645]


@pytest.fixture(autouse=True)
def ambiente(monkeypatch, tmp_path):
    monkeypatch.setenv("MUNICIPIO_YAML", str(RAIZ / "config" / "municipio.yaml"))
    monkeypatch.setenv("ANON_DIR", str(tmp_path / "anon"))
    monkeypatch.setenv("RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("MAPILLARY_TOKEN", "token-de-teste")
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


def _registo(identificador, lon= -8.6475, lat= 40.6425):
    return ImageRecord(
        "mapillary",
        identificador,
        "autor",
        "CC BY-SA 4.0",
        f"https://www.mapillary.com/app/?pKey={identificador}",
        datetime(2026, 1, 1, tzinfo=UTC),
        lon,
        lat,
        45.0,
        "perspective",
        f"https://exemplo.invalido/{identificador}.jpg",
    )


class Anonimizador:
    def __call__(self, imagem):
        return imagem.copy()


class Detetor:
    def detect(self, image_id, image):
        return [Detection(image_id, "iluminacao", "candeeiro", (90.0, 20.0, 110.0, 80.0), 0.9, False)]


def _descarregar(registo):
    return np.full((100, 200, 3), 90, np.uint8)


def _executar(tmp_path, sessao, analise, detetor= None):
    return processar_analise(
        sessao, analise, Anonimizador(), detetor or Detetor(), MUNICIPIO, CLASSES,
        tmp_path / "raw", tmp_path / "anon", saida=io.StringIO(),
    )


def _zona(sessao, nome= "Zona"):
    return analises.criar(sessao, nome, {"fonte": "mapillary", "bbox": BBOX})


def _listar(monkeypatch, registos):
    monkeypatch.setattr(mapillary, "fetch_images", lambda bbox, token: registos)
    monkeypatch.setattr(worker, "processar", functools.partial(run.processar, baixar=_descarregar))


def test_zona_valida_cria_analise_na_fila(cliente, sessao):
    resposta= cliente.post("/analises/zona", json={"bbox": BBOX})
    assert resposta.status_code == 201
    dados= resposta.json()
    assert dados["url"] == f"/a/{dados['token']}"
    assert dados["estado"] == "na_fila"
    detalhe= cliente.get(f"/analises/{dados['token']}").json()
    assert detalhe["parametros"] == {"fonte": "mapillary", "bbox": BBOX}
    assert detalhe["nome"] == "Mapillary, 40.6425, -8.6475"


def test_zona_com_nome_e_limpo(cliente, sessao):
    token= cliente.post("/analises/zona", json={"bbox": BBOX, "nome": "  Rua da Pega  "}).json()["token"]
    assert cliente.get(f"/analises/{token}").json()["nome"] == "Rua da Pega"


def test_zona_com_ordem_invalida_recusa(cliente, sessao):
    resposta= cliente.post("/analises/zona", json={"bbox": [-8.645, 40.64, -8.65, 40.645]})
    assert resposta.status_code == 422
    assert "mínimos" in resposta.json()["detail"]


def test_zona_fora_de_limites_recusa(cliente, sessao):
    resposta= cliente.post("/analises/zona", json={"bbox": [-200, 40.64, -8.645, 40.645]})
    assert resposta.status_code == 422
    assert "fora de limites" in resposta.json()["detail"]


def test_zona_grande_demais_recusa(cliente, sessao):
    resposta= cliente.post("/analises/zona", json={"bbox": [-8.7, 40.6, -8.65, 40.65]})
    assert resposta.status_code == 422
    assert resposta.json()["detail"] == "A zona é grande demais: no máximo cerca de 2 km de lado."


def test_zona_com_tres_valores_recusa(cliente, sessao):
    assert cliente.post("/analises/zona", json={"bbox": [-8.65, 40.64, -8.645]}).status_code == 422


def test_worker_zona_sem_imagens_falha(tmp_path, sessao, monkeypatch):
    _listar(monkeypatch, [])
    analise= _zona(sessao)
    assert _executar(tmp_path, sessao, analise) is False
    assert analise.estado == "falhou"
    assert analise.erro == "Não há imagens do Mapillary nesta zona"


def test_worker_zona_com_imagens_conclui(tmp_path, sessao, monkeypatch):
    _listar(monkeypatch, [_registo("m1"), _registo("m2", lon= -8.6474)])
    analise= _zona(sessao)
    assert _executar(tmp_path, sessao, analise) is True
    assert analise.estado == "concluida"
    assert analise.total == 2
    assert analise.n_elementos >= 1
    imagens= sessao.scalars(select(Imagem).where(Imagem.analise_id == analise.id)).all()
    assert sorted(i.id_fonte for i in imagens) == ["m1", "m2"]
    assert all(i.fonte == "mapillary" for i in imagens)


def test_worker_zona_sem_imagens_novas_falha(tmp_path, sessao, monkeypatch):
    _listar(monkeypatch, [_registo("m1")])
    assert _executar(tmp_path, sessao, _zona(sessao, "Primeira")) is True
    segunda= _zona(sessao, "Segunda")
    assert _executar(tmp_path, sessao, segunda) is False
    assert segunda.erro == "A imagem desta zona já está noutra análise"


def test_worker_zona_com_imagens_repetidas_avisa(tmp_path, sessao, monkeypatch):
    _listar(monkeypatch, [_registo("m1")])
    assert _executar(tmp_path, sessao, _zona(sessao, "Primeira")) is True
    _listar(monkeypatch, [_registo("m1"), _registo("m2", lon= -8.6474)])
    segunda= _zona(sessao, "Segunda")
    assert _executar(tmp_path, sessao, segunda) is True
    assert segunda.estado == "concluida"
    assert "1 imagem já existia noutra análise e ficou de fora" in segunda.avisos


def test_worker_zona_com_demasiadas_imagens_falha_sem_processar(tmp_path, sessao, monkeypatch):
    monkeypatch.setenv("MAX_IMAGENS_ZONA", "2")
    _listar(monkeypatch, [_registo("m1"), _registo("m2", lon= -8.6474), _registo("m3", lon= -8.6473)])
    analise= _zona(sessao)
    assert _executar(tmp_path, sessao, analise) is False
    assert analise.estado == "falhou"
    assert analise.erro == "A zona tem 3 imagens, mais do que o máximo de 2 por análise. Escolha uma zona mais pequena."
    assert sessao.scalars(select(Imagem).where(Imagem.analise_id == analise.id)).all() == []


def test_worker_zona_no_limite_conclui(tmp_path, sessao, monkeypatch):
    monkeypatch.setenv("MAX_IMAGENS_ZONA", "2")
    _listar(monkeypatch, [_registo("m1"), _registo("m2", lon= -8.6474)])
    assert _executar(tmp_path, sessao, _zona(sessao)) is True


def test_worker_zona_sem_token_falha(tmp_path, sessao, monkeypatch):
    monkeypatch.delenv("MAPILLARY_TOKEN", raising=False)
    analise= _zona(sessao)
    assert _executar(tmp_path, sessao, analise) is False
    assert analise.estado == "falhou"
    assert analise.erro == "O worker não tem o MAPILLARY_TOKEN configurado"
