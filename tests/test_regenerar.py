import io
from datetime import UTC, datetime

import cv2
import numpy as np

from pipeline.anonymize.egoblur import caminho_anon
from pipeline.errors import ErroPipeline
from pipeline.models import ImageRecord
from pipeline.run import regenerar


def _registo(identificador):
    return ImageRecord(
        "mapillary", identificador, "autor", "CC BY-SA 4.0", f"http://x/{identificador}",
        datetime(2026, 1, 1, tzinfo=UTC), -8.65, 40.64, 10.0, "perspective", "http://img",
    )


class Anonimizador:
    def __init__(self):
        self.chamadas= 0

    def __call__(self, imagem):
        self.chamadas+= 1
        return imagem.copy()


def _baixar(registo):
    if registo.id_fonte == "mau":
        raise ErroPipeline("sem rede")
    return np.zeros((40, 60, 3), dtype=np.uint8)


def _nunca(_):
    raise AssertionError("não devia descarregar")


def _guardar(pasta, identificador, valor= 50):
    pasta.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(caminho_anon(pasta, _registo(identificador))), np.full((10, 10, 3), valor, dtype=np.uint8))


def test_regenera_so_as_imagens_em_falta(tmp_path):
    pasta= tmp_path / "anon"
    _guardar(pasta, "b")
    registadas= {"a": "/outro/sitio/mapillary_a.jpg", "b": "/outro/sitio/mapillary_b.jpg"}
    anonimizador= Anonimizador()
    resultado= regenerar(
        registadas, [_registo("a"), _registo("b")], anonimizador, pasta, _baixar, saida=io.StringIO()
    )
    assert resultado == (1, 0)
    assert anonimizador.chamadas == 1
    assert caminho_anon(pasta, _registo("a")).is_file()
    assert int(cv2.imread(str(caminho_anon(pasta, _registo("b")))).mean()) == 50


def test_grava_so_a_versao_anonimizada(tmp_path):
    original= np.full((40, 60, 3), 200, dtype=np.uint8)
    anonima= np.full((40, 60, 3), 7, dtype=np.uint8)
    regenerar(
        {"a": "x/mapillary_a.jpg"}, [_registo("a")], lambda imagem: anonima, tmp_path / "anon",
        lambda _: original, saida=io.StringIO(),
    )
    assert int(cv2.imread(str(caminho_anon(tmp_path / "anon", _registo("a")))).mean()) < 20


def test_conta_indisponiveis(tmp_path):
    registadas= {"c": "x/mapillary_c.jpg", "mau": "x/mapillary_mau.jpg"}
    resultado= regenerar(
        registadas, [_registo("mau")], Anonimizador(), tmp_path / "anon", _baixar, saida=io.StringIO()
    )
    assert resultado == (0, 2)


def test_sem_nada_em_falta_nao_descarrega(tmp_path):
    pasta= tmp_path / "anon"
    _guardar(pasta, "a")
    anonimizador= Anonimizador()
    resultado= regenerar(
        {"a": "x/mapillary_a.jpg"}, [_registo("a")], anonimizador, pasta, _nunca, saida=io.StringIO()
    )
    assert resultado == (0, 0)
    assert anonimizador.chamadas == 0
