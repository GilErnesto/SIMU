import io
import json
from datetime import UTC, datetime

import cv2
import numpy as np
import pytest
import requests

from pipeline import checkpoint
from pipeline.anonymize.egoblur import caminho_anon
from pipeline.errors import ErroPipeline
from pipeline.ingest import mapillary
from pipeline.models import Detection, ImageRecord
from pipeline.run import processar


def _registo(identificador, **extra):
    return ImageRecord(
        "mapillary", identificador, "autor", "CC BY-SA 4.0", f"http://x/{identificador}",
        datetime(2026, 1, 1, tzinfo=UTC), -8.65, 40.64, 10.0, "perspective", "http://img", **extra,
    )


class DetetorFalso:
    def __init__(self):
        self.vistas= []

    def detect(self, image_id, image):
        self.vistas.append(image_id)
        return [Detection(image_id, "iluminacao", "candeeiro", (1.0, 2.0, 3.0, 4.0), 0.9, False)]


class Anonimizador:
    def __init__(self):
        self.chamadas= 0

    def __call__(self, imagem):
        self.chamadas+= 1
        return imagem.copy()


def _baixar_com_falha(registo):
    if registo.id_fonte == "mau":
        raise ErroPipeline("sem rede")
    return np.zeros((40, 60, 3), dtype=np.uint8)


def _nunca(_):
    raise AssertionError("não devia descarregar")


def _executar(tmp_path, imagens, baixar, anonimizador=None, detetor=None):
    anonimizador= anonimizador or Anonimizador()
    detetor= detetor or DetetorFalso()
    resultado, falhas= processar(
        imagens, anonimizador, detetor, tmp_path / "anon", tmp_path / "anon" / "cp.jsonl", baixar,
        saida=io.StringIO(),
    )
    return resultado, falhas, anonimizador, detetor


def test_imagem_com_falha_e_ignorada_e_contada(tmp_path):
    imagens= [_registo("a"), _registo("mau"), _registo("b")]
    resultado, falhas, _, _= _executar(tmp_path, imagens, _baixar_com_falha)
    assert sorted(resultado) == ["a", "b"]
    assert falhas == ["mau"]
    registo, deteccoes= resultado["a"]
    assert (registo.height, registo.width) == (40, 60)
    assert registo.caminho_anon.endswith("mapillary_a.jpg")
    assert len(deteccoes) == 1


def test_so_a_versao_anonimizada_vai_para_disco(tmp_path):
    original= np.full((40, 60, 3), 200, dtype=np.uint8)
    anonima= np.full((40, 60, 3), 7, dtype=np.uint8)

    class Troca:
        def __call__(self, imagem):
            assert imagem is original
            return anonima

    _executar(tmp_path, [_registo("a")], lambda _: original, Troca())
    guardada= cv2.imread(str(caminho_anon(tmp_path / "anon", _registo("a"))))
    assert int(guardada.mean()) < 20


def test_retoma_pelo_checkpoint_sem_descarregar(tmp_path):
    imagens= [_registo("a"), _registo("b")]
    _executar(tmp_path, imagens, _baixar_com_falha)
    detetor= DetetorFalso()
    resultado, falhas, anonimizador, _= _executar(tmp_path, imagens, _nunca, detetor=detetor)
    assert sorted(resultado) == ["a", "b"]
    assert falhas == []
    assert detetor.vistas == []
    assert anonimizador.chamadas == 0
    assert resultado["a"][0].width == 60


def test_reaproveita_imagem_anonimizada_sem_checkpoint(tmp_path):
    imagens= [_registo("a")]
    _executar(tmp_path, imagens, _baixar_com_falha)
    (tmp_path / "anon" / "cp.jsonl").unlink()
    detetor= DetetorFalso()
    resultado, _, anonimizador, _= _executar(tmp_path, [_registo("a")], _nunca, detetor=detetor)
    assert list(resultado) == ["a"]
    assert detetor.vistas == ["mapillary:a"]
    assert anonimizador.chamadas == 0
    assert resultado["a"][0].caminho_anon.endswith("mapillary_a.jpg")


def test_checkpoint_tolera_linha_truncada(tmp_path):
    ficheiro= tmp_path / "cp.jsonl"
    checkpoint.append(ficheiro, _registo("a", width=60, height=40), [])
    with ficheiro.open("a") as f:
        f.write('{"imagem": {"fonte": "mapi')
    lidas= checkpoint.load(ficheiro)
    assert list(lidas) == ["a"]


def test_checkpoint_ida_e_volta(tmp_path):
    ficheiro= tmp_path / "cp.jsonl"
    registo= _registo("a", width=60, height=40, caminho_anon="data/anon/x.jpg")
    deteccao= Detection(registo.id, "sinal", "stop", (1.0, 2.0, 3.0, 4.0), 0.5, True)
    checkpoint.append(ficheiro, registo, [deteccao])
    lido, deteccoes= checkpoint.load(ficheiro)["a"]
    assert lido == registo
    assert deteccoes == [deteccao]
    assert isinstance(deteccoes[0].bbox_xyxy, tuple)
    json.loads(ficheiro.read_text().splitlines()[0])


def test_checkpoint_inexistente(tmp_path):
    assert checkpoint.load(tmp_path / "nada.jsonl") == {}


class Resposta:
    def __init__(self, conteudo=b"", erro=None):
        self.content= conteudo
        self.erro= erro

    def raise_for_status(self):
        if self.erro:
            raise self.erro


class SessaoInstavel:
    def __init__(self, falhas, jpg):
        self.falhas= falhas
        self.jpg= jpg
        self.pedidos= 0
        self.timeouts= []

    def get(self, url, timeout=None):
        self.pedidos+= 1
        self.timeouts.append(timeout)
        if self.pedidos <= self.falhas:
            raise requests.ConnectTimeout("sem ligação")
        return Resposta(self.jpg)


@pytest.fixture
def jpg():
    return cv2.imencode(".jpg", np.zeros((8, 8, 3), dtype=np.uint8))[1].tobytes()


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(mapillary.time, "sleep", lambda _: None)


def test_download_tenta_de_novo_e_recupera(jpg):
    sessao= SessaoInstavel(2, jpg)
    imagem= mapillary.download(_registo("a"), sessao)
    assert imagem.shape == (8, 8, 3)
    assert sessao.pedidos == 3
    assert isinstance(sessao.timeouts[0], tuple)


def test_download_desiste_depois_das_tentativas(jpg):
    sessao= SessaoInstavel(99, jpg)
    with pytest.raises(ErroPipeline, match="3 tentativas") as erro:
        mapillary.download(_registo("a"), sessao)
    assert sessao.pedidos == 3
    assert "http://img" not in str(erro.value)
