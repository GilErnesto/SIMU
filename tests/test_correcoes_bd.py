import json
import os
import uuid

import cv2
import numpy as np
import pytest
from geoalchemy2 import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from pipeline.catalog.write import Analise, Correcao, Elemento, Imagem, Observacao, ensure_schema
from training.correcoes import main

URL_BD= os.environ.get("TEST_DATABASE_URL")
precisa_bd= pytest.mark.skipif(not URL_BD, reason="TEST_DATABASE_URL não definido")
LON, LAT= -8.65, 40.64


def imagem(sessao, analise, camera_type, caminho) -> Imagem:
    img= Imagem(
        fonte="teste",
        id_fonte=uuid.uuid4().hex,
        autor="a",
        licenca="CC BY-SA 4.0",
        url_origem="http://x",
        camera_type=camera_type,
        caminho_anon=caminho,
        analise_id=analise.id,
    )
    sessao.add(img)
    sessao.flush()
    return img


def elemento(sessao, analise, img, classe, estado, bbox, classe_obs=None) -> Elemento:
    el= Elemento(
        categoria="iluminacao",
        classe=classe,
        geom=WKTElement(f"POINT({LON + bbox[0] * 1e-5} {LAT})", srid=4326),
        confianca=0.8,
        estado=estado,
        metodo_geo="triangulacao",
        n_observacoes=1,
        analise_id=analise.id,
    )
    sessao.add(el)
    sessao.flush()
    sessao.add(
        Observacao(
            elemento_id=el.id,
            imagem_id=img.id,
            bbox=bbox,
            classe=classe_obs or classe,
            confianca=0.8,
            bearing=10.0,
        )
    )
    sessao.flush()
    return el


@pytest.fixture
def cenario(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", URL_BD)
    anon= tmp_path / "anon"
    anon.mkdir()
    cv2.imwrite(str(anon / "perspetiva.jpg"), np.full((300, 400, 3), 128, np.uint8))
    engine= create_engine(URL_BD)
    ensure_schema(engine)
    with Session(engine) as sessao:
        analise= Analise(token=uuid.uuid4().hex, nome="teste", estado="concluida")
        sessao.add(analise)
        sessao.flush()
        perspetiva= imagem(sessao, analise, "perspective", "perspetiva.jpg")
        panoramica= imagem(sessao, analise, "spherical", None)
        elemento(sessao, analise, perspetiva, "candeeiro", "validado", [20, 20, 120, 140])
        b= elemento(sessao, analise, perspetiva, "poste_luz", "corrigido", [150, 20, 250, 140], classe_obs="luz")
        sessao.add(Correcao(elemento_id=b.id, campo="classe", valor_antigo="luz", valor_novo="poste_luz", autor="tecnica"))
        elemento(sessao, analise, perspetiva, "luz", "rejeitado", [20, 150, 120, 290])
        elemento(sessao, analise, perspetiva, "luz", "auto", [150, 150, 250, 290])
        e= elemento(sessao, analise, perspetiva, "luz", "corrigido", [280, 20, 380, 140])
        sessao.add(Correcao(elemento_id=e.id, campo="posicao", valor_antigo=None, valor_novo="40.64,-8.65", autor="tecnica"))
        elemento(sessao, analise, panoramica, "candeeiro", "validado", [10, 10, 50, 50])
        sessao.commit()
        token= analise.token
        posicao_e= to_shape(e.geom)
    yield {"anon": anon, "token": token, "posicao_e": posicao_e}
    with engine.begin() as ligacao:
        ligacao.execute(text("TRUNCATE correcao, observacao, elemento, imagem, analise CASCADE"))
    engine.dispose()


def correr(cenario, tmp_path, *extra) -> tuple[int, object, object]:
    saida= tmp_path / "saida"
    referencia= tmp_path / "ref.geojson"
    codigo= main(
        [
            "--saida", str(saida),
            "--anon-dir", str(cenario["anon"]),
            "--referencia", str(referencia),
            "--analise", cenario["token"],
            *extra,
        ]
    )
    return codigo, saida, referencia


def recortes(saida, classe) -> list:
    return list(saida.glob(f"recortes/*/{classe}/*.jpg"))


@precisa_bd
def test_recortes_so_das_classes_revistas_e_dos_negativos(cenario, tmp_path):
    codigo, saida, _ = correr(cenario, tmp_path)
    assert codigo == 0
    assert len(recortes(saida, "candeeiro")) == 1
    assert len(recortes(saida, "poste_luz")) == 1
    assert len(recortes(saida, "nao_luz")) == 1
    assert sorted(p.parent.name for p in saida.glob("recortes/*/*/*.jpg")) == ["candeeiro", "nao_luz", "poste_luz"]


@precisa_bd
def test_caminho_absoluto_do_contentor_resolve_se_em_anon_dir(cenario, tmp_path):
    engine= create_engine(URL_BD)
    with engine.begin() as ligacao:
        ligacao.execute(text("UPDATE imagem SET caminho_anon= '/app/data/anon/perspetiva.jpg' WHERE caminho_anon= 'perspetiva.jpg'"))
    engine.dispose()
    codigo, saida, _ = correr(cenario, tmp_path)
    assert codigo == 0
    assert len(recortes(saida, "candeeiro")) == 1
    assert len(recortes(saida, "poste_luz")) == 1
    assert len(recortes(saida, "nao_luz")) == 1


@precisa_bd
def test_referencia_so_com_a_posicao_indicada_pelo_tecnico(cenario, tmp_path):
    codigo, _, referencia= correr(cenario, tmp_path)
    assert codigo == 0
    dados= json.loads(referencia.read_text(encoding="utf-8"))
    assert len(dados["features"]) == 1
    ponto= dados["features"][0]["geometry"]["coordinates"]
    assert ponto[0] == pytest.approx(cenario["posicao_e"].x)
    assert ponto[1] == pytest.approx(cenario["posicao_e"].y)


@precisa_bd
def test_dotenv_nao_sobrepoe_a_url_do_teste(cenario, tmp_path):
    correr(cenario, tmp_path)
    assert os.environ["DATABASE_URL"] == URL_BD
