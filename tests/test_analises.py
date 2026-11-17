import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from pipeline.catalog import analises
from pipeline.catalog.write import (
    Analise,
    Elemento,
    Imagem,
    atribuir_analise_inicial,
    ensure_schema,
    write_catalog,
)
from pipeline.config import load_classes
from pipeline.models import Detection, Element, ImageRecord, Observation

CLASSES= load_classes(Path(__file__).parents[1] / "config" / "classes.yaml")
URL_BD= os.environ.get("TEST_DATABASE_URL")
pytestmark= pytest.mark.skipif(not URL_BD, reason="TEST_DATABASE_URL não definido")


@pytest.fixture
def sessao():
    engine= create_engine(URL_BD)
    ensure_schema(engine)
    with engine.connect() as ligacao:
        transacao= ligacao.begin()
        with Session(ligacao, join_transaction_mode="create_savepoint") as s:
            yield s
        transacao.rollback()


def _registo(identificador, lon= -8.65, lat= 40.64):
    return ImageRecord(
        "upload", identificador, "Utilizador", "Dados do utilizador", "",
        datetime(2026, 1, 1, tzinfo=UTC), lon, lat, 0.0, "perspective", "x",
        width=1000, height=800, caminho_anon=f"data/anon/{identificador}.jpg",
    )


def _elemento(registo, lon= -8.65, lat= 40.64):
    deteccao= Detection(registo.id, "iluminacao", "candeeiro", (1, 2, 3, 4), 0.8, False)
    return Element(
        "iluminacao", "candeeiro", lon, lat, False, "monocular", [Observation(deteccao, registo, 1.0)]
    )


def test_criar_e_obter_por_token(sessao):
    analise= analises.criar(sessao, "Teste", {"fps": 2}, ["aviso"])
    assert len(analise.token) >= 8
    assert analise.estado == "na_fila"
    encontrada= analises.obter_por_token(sessao, analise.token)
    assert encontrada.id == analise.id
    assert encontrada.avisos == ["aviso"]
    assert analises.obter_por_token(sessao, "nao-existe") is None


def test_tokens_sao_diferentes():
    assert len({analises.novo_token() for _ in range(50)}) == 50


def test_fila_por_ordem_e_cada_analise_so_uma_vez(sessao):
    a= analises.criar(sessao, "A")
    b= analises.criar(sessao, "B")
    primeira= analises.reclamar_proxima(sessao)
    assert primeira.id == a.id
    assert primeira.estado == "a_processar"
    assert primeira.iniciada_em is not None
    assert analises.reclamar_proxima(sessao).id == b.id
    assert analises.reclamar_proxima(sessao) is None


def test_recuperar_interrompidas(sessao):
    analises.criar(sessao, "A")
    analises.reclamar_proxima(sessao)
    assert analises.recuperar_interrompidas(sessao) == 1
    assert analises.reclamar_proxima(sessao).nome == "A"


def test_progresso_concluir_e_falhar(sessao):
    a= analises.criar(sessao, "A")
    analises.registar_progresso(sessao, a, 3, 10)
    assert (a.feitas, a.total) == (3, 10)
    analises.concluir(sessao, a, 5, ["nota"])
    assert (a.estado, a.n_elementos, a.avisos) == ("concluida", 5, ["nota"])
    assert a.concluida_em is not None
    b= analises.criar(sessao, "B")
    analises.falhar(sessao, b, "x" * 900, ["aviso"])
    assert b.estado == "falhou"
    assert len(b.erro) == 500
    assert b.avisos == ["aviso"]


def test_criar_ou_obter_e_idempotente(sessao):
    a= analises.criar_ou_obter(sessao, "zona-123", "Mapillary")
    b= analises.criar_ou_obter(sessao, "zona-123", "outro nome")
    assert a.id == b.id
    assert a.estado == "concluida"


def test_analises_diferentes_nao_juntam_elementos_no_mesmo_sitio(sessao):
    a= analises.criar(sessao, "A")
    b= analises.criar(sessao, "B")
    write_catalog(sessao, CLASSES, [_registo("a-1")], [_elemento(_registo("a-1"))], analise_id=a.id)
    write_catalog(sessao, CLASSES, [_registo("b-1")], [_elemento(_registo("b-1"))], analise_id=b.id)
    por_analise= {x.analise_id for x in sessao.scalars(select(Elemento))}
    assert {a.id, b.id} <= por_analise
    assert sessao.scalar(select(Elemento.id).where(Elemento.analise_id == a.id).limit(1)) is not None
    contagens= [
        len(list(sessao.scalars(select(Elemento).where(Elemento.analise_id == x.id)))) for x in (a, b)
    ]
    assert contagens == [1, 1]


def test_mesma_analise_continua_a_juntar_elementos(sessao):
    a= analises.criar(sessao, "A")
    write_catalog(sessao, CLASSES, [_registo("a-1")], [_elemento(_registo("a-1"))], analise_id=a.id)
    write_catalog(
        sessao, CLASSES, [_registo("a-2")], [_elemento(_registo("a-2", -8.65001, 40.64001), -8.65001, 40.64001)],
        analise_id=a.id,
    )
    elementos= list(sessao.scalars(select(Elemento).where(Elemento.analise_id == a.id)))
    assert len(elementos) == 1
    assert elementos[0].n_observacoes == 2


def test_imagens_ficam_ligadas_a_analise(sessao):
    a= analises.criar(sessao, "A")
    write_catalog(sessao, CLASSES, [_registo("a-1")], [_elemento(_registo("a-1"))], analise_id=a.id)
    imagem= sessao.scalar(select(Imagem).where(Imagem.id_fonte == "a-1"))
    assert imagem.analise_id == a.id


def test_atualizar_contagens(sessao):
    a= analises.criar(sessao, "A")
    write_catalog(sessao, CLASSES, [_registo("a-1")], [_elemento(_registo("a-1"))], analise_id=a.id)
    analises.atualizar_contagens(sessao, a)
    assert (a.total, a.feitas, a.n_elementos) == (1, 1, 1)


def test_catalogo_antigo_sem_analise_passa_para_a_inicial(sessao):
    write_catalog(sessao, CLASSES, [_registo("velho-1")], [_elemento(_registo("velho-1"))])
    antes= sessao.scalar(select(Imagem).where(Imagem.id_fonte == "velho-1"))
    assert antes.analise_id is None
    atribuir_analise_inicial(sessao)
    inicial= analises.obter_por_token(sessao, "inicial")
    assert inicial.nome == "Catálogo anterior"
    assert inicial.estado == "concluida"
    assert sessao.scalar(select(Imagem).where(Imagem.id_fonte == "velho-1")).analise_id == inicial.id
    assert inicial.total >= 1 and inicial.n_elementos >= 1


def test_sem_orfaos_nao_cria_analise_inicial(sessao):
    sessao.query(Analise).filter(Analise.token == "inicial").delete()
    existe_orfao= sessao.scalar(select(Imagem.id).where(Imagem.analise_id.is_(None)).limit(1))
    if existe_orfao is None:
        atribuir_analise_inicial(sessao)
        assert analises.obter_por_token(sessao, "inicial") is None
