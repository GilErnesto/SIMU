import io
import os
from pathlib import Path

import pytest
from PIL import Image
from pyproj import Transformer
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from pipeline.catalog import analises
from pipeline.catalog.write import Elemento, Imagem, ensure_schema
from pipeline.config import load_classes, load_municipio
from pipeline.models import Detection
from pipeline.worker import processar_analise

RAIZ= Path(__file__).parents[1]
CLASSES= load_classes(RAIZ / "config" / "classes.yaml")
MUNICIPIO= load_municipio(RAIZ / "config" / "municipio.yaml")
URL_BD= os.environ.get("TEST_DATABASE_URL")
pytestmark= pytest.mark.skipif(not URL_BD, reason="TEST_DATABASE_URL não definido")
PARA_GRAUS= Transformer.from_crs(MUNICIPIO.crs_metrico, "EPSG:4326", always_xy=True)
PARA_METROS= Transformer.from_crs("EPSG:4326", MUNICIPIO.crs_metrico, always_xy=True)
X0, Y0= PARA_METROS.transform(-8.65, 40.64)


@pytest.fixture
def sessao():
    engine= create_engine(URL_BD)
    ensure_schema(engine)
    with engine.connect() as ligacao:
        transacao= ligacao.begin()
        with Session(ligacao, join_transaction_mode="create_savepoint") as s:
            yield s
        transacao.rollback()


def _dms(valor):
    valor= abs(valor)
    graus= int(valor)
    minutos= (valor - graus) * 60
    return float(graus), float(int(minutos)), (minutos - int(minutos)) * 60


def _foto(caminho, x, y, rumo):
    lon, lat= PARA_GRAUS.transform(x, y)
    exif= Image.Exif()
    exif[0x8825]= {
        1: "N" if lat >= 0 else "S",
        2: _dms(lat),
        3: "E" if lon >= 0 else "W",
        4: _dms(lon),
        17: rumo,
    }
    exif[0x8769]= {36867: "2026:05:01 10:00:00"}
    Image.new("RGB", (200, 100), (90, 90, 90)).save(caminho, exif=exif)


class Anonimizador:
    def __init__(self):
        self.chamadas= 0

    def __call__(self, imagem):
        self.chamadas+= 1
        return imagem.copy()


class Detetor:
    def detect(self, image_id, image):
        return [Detection(image_id, "iluminacao", "candeeiro", (90.0, 40.0, 110.0, 60.0), 0.9, False)]


class DetetorQueFalha:
    def detect(self, image_id, image):
        raise RuntimeError("memória da GPU esgotada")


def _preparar(tmp_path, sessao, fotos):
    analise= analises.criar(sessao, "Teste")
    pasta= tmp_path / "raw" / analise.token
    pasta.mkdir(parents=True)
    for nome, x, y, rumo in fotos:
        _foto(pasta / nome, x, y, rumo)
    return analise, pasta


def _executar(tmp_path, sessao, analise, detetor= None, anonimizador= None):
    return processar_analise(
        sessao, analise, anonimizador or Anonimizador(), detetor or Detetor(), MUNICIPIO, CLASSES,
        tmp_path / "raw", tmp_path / "anon", saida=io.StringIO(),
    )


def test_analise_completa_gera_elementos_e_apaga_os_originais(tmp_path, sessao):
    analise, pasta= _preparar(
        tmp_path, sessao, [("0001_a.jpg", X0, Y0, 45.0), ("0002_b.jpg", X0 + 10, Y0, 315.0)]
    )
    anonimizador= Anonimizador()
    assert _executar(tmp_path, sessao, analise, anonimizador= anonimizador) is True
    assert analise.estado == "concluida"
    assert (analise.total, analise.feitas, analise.n_elementos) == (2, 2, 1)
    assert analise.concluida_em is not None
    assert anonimizador.chamadas == 2
    assert not pasta.exists()
    assert sorted(p.name for p in (tmp_path / "anon").glob("*.jpg")) == [
        f"upload_{analise.token}-00001.jpg",
        f"upload_{analise.token}-00002.jpg",
    ]
    elemento= sessao.scalar(select(Elemento).where(Elemento.analise_id == analise.id))
    assert (elemento.categoria, elemento.classe, elemento.metodo_geo) == ("iluminacao", "candeeiro", "triangulacao")
    imagens= list(sessao.scalars(select(Imagem).where(Imagem.analise_id == analise.id)))
    assert len(imagens) == 2
    assert all(i.fonte == "upload" and i.licenca == "Dados do utilizador" for i in imagens)


def test_posicao_do_elemento_e_a_do_ponto_triangulado(tmp_path, sessao):
    from geoalchemy2.shape import to_shape

    analise, _= _preparar(
        tmp_path, sessao, [("0001_a.jpg", X0, Y0, 45.0), ("0002_b.jpg", X0 + 10, Y0, 315.0)]
    )
    _executar(tmp_path, sessao, analise)
    ponto= to_shape(sessao.scalar(select(Elemento).where(Elemento.analise_id == analise.id)).geom)
    x, y= PARA_METROS.transform(ponto.x, ponto.y)
    assert (x, y) == pytest.approx((X0 + 5, Y0 + 5), abs=1.0)


def test_sem_imagens_utilizaveis_falha_e_guarda_os_ficheiros(tmp_path, sessao):
    analise= analises.criar(sessao, "Sem GPS")
    pasta= tmp_path / "raw" / analise.token
    pasta.mkdir(parents=True)
    Image.new("RGB", (32, 32)).save(pasta / "0001_x.jpg")
    assert _executar(tmp_path, sessao, analise) is False
    assert analise.estado == "falhou"
    assert "Nenhuma imagem utilizável" in analise.erro
    assert any("sem GPS" in a for a in analise.avisos)
    assert pasta.exists()


def test_erro_no_detetor_marca_falha_sem_derrubar_o_worker(tmp_path, sessao):
    analise, pasta= _preparar(
        tmp_path, sessao, [("0001_a.jpg", X0, Y0, 45.0), ("0002_b.jpg", X0 + 10, Y0, 315.0)]
    )
    assert _executar(tmp_path, sessao, analise, detetor= DetetorQueFalha()) is False
    assert analise.estado == "falhou"
    assert "RuntimeError" in analise.erro and "GPU" in analise.erro
    assert pasta.exists()


def test_pasta_de_ficheiros_em_falta(tmp_path, sessao):
    analise= analises.criar(sessao, "Perdida")
    assert _executar(tmp_path, sessao, analise) is False
    assert analise.estado == "falhou"
    assert "já não existem" in analise.erro


def test_so_a_versao_anonimizada_vai_para_a_pasta_publica(tmp_path, sessao):
    analise, _= _preparar(tmp_path, sessao, [("0001_a.jpg", X0, Y0, 45.0), ("0002_b.jpg", X0 + 10, Y0, 315.0)])

    class Escurecer:
        def __call__(self, imagem):
            return imagem * 0

    _executar(tmp_path, sessao, analise, anonimizador= Escurecer())
    import cv2

    guardada= cv2.imread(str(tmp_path / "anon" / f"upload_{analise.token}-00001.jpg"))
    assert guardada.max() < 10
