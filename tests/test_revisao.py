import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from geoalchemy2 import WKTElement
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.deps import get_classes, get_municipio, get_session
from backend.main import app
from pipeline.catalog import revisao
from pipeline.catalog.revisao import ErroRevisao
from pipeline.catalog.write import Analise, Correcao, Elemento, Imagem, Observacao, ensure_schema

URL_BD= os.environ.get("TEST_DATABASE_URL")
precisa_bd= pytest.mark.skipif(not URL_BD, reason="TEST_DATABASE_URL não definido")
RAIZ= Path(__file__).parents[1]
LON, LAT= -8.65, 40.64
CRS= "EPSG:3763"


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
    app.dependency_overrides.clear()


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    monkeypatch.setenv("MUNICIPIO_YAML", str(RAIZ / "config" / "municipio.yaml"))
    monkeypatch.setenv("ANON_DIR", str(tmp_path / "anon"))
    get_municipio.cache_clear()
    get_classes.cache_clear()
    return TestClient(app)


def nova_analise(sessao) -> Analise:
    analise= Analise(token=uuid.uuid4().hex, nome="teste", estado="concluida")
    sessao.add(analise)
    sessao.flush()
    return analise


def criar_elemento(sessao, analise, dx_m, dy_m, fotos, categoria="iluminacao", classe="luz", estado="auto", imagens=None) -> Elemento:
    imagens= imagens if imagens is not None else {}
    elemento= Elemento(
        categoria=categoria,
        classe=classe,
        geom=WKTElement(f"POINT({LON + dx_m / 84000} {LAT + dy_m / 111000})", srid=4326),
        confianca=0.8,
        estado=estado,
        metodo_geo="triangulacao",
        n_observacoes=len(fotos),
        analise_id=analise.id,
    )
    sessao.add(elemento)
    sessao.flush()
    for chave in fotos:
        if chave not in imagens:
            imagem= Imagem(fonte="teste", id_fonte=uuid.uuid4().hex, autor="a", licenca="CC", url_origem="http://x", analise_id=analise.id)
            sessao.add(imagem)
            sessao.flush()
            imagens[chave]= imagem
        sessao.add(Observacao(elemento_id=elemento.id, imagem_id=imagens[chave].id, bbox=[1, 2, 3, 4], classe=classe, confianca=0.8, bearing=10.0))
    sessao.flush()
    return elemento


def correcoes(sessao, elemento_id):
    return [(c.campo, c.valor_novo) for c in sessao.scalars(select(Correcao).where(Correcao.elemento_id == elemento_id))]


@precisa_bd
def test_juntar_move_observacoes_e_rejeita_a_origem(sessao):
    analise= nova_analise(sessao)
    a= criar_elemento(sessao, analise, 0, 0, ["x", "y"])
    b= criar_elemento(sessao, analise, 4, 0, ["z"])
    destino= revisao.juntar(sessao, a.id, b.id, "tecnica")
    sessao.refresh(b)
    assert destino.id == a.id
    assert destino.n_observacoes == 3
    assert destino.estado == "corrigido"
    assert b.estado == "rejeitado"
    assert b.n_observacoes == 0
    assert sessao.scalar(select(Observacao).where(Observacao.elemento_id == b.id)) is None
    assert ("juntar", f"elemento {b.id}") in correcoes(sessao, a.id)
    assert ("juntado_em", str(a.id)) in correcoes(sessao, b.id)
    assert ("estado", "rejeitado") in correcoes(sessao, b.id)


@precisa_bd
def test_juntar_posicao_pesa_pelo_numero_de_fotografias(sessao):
    from geoalchemy2.shape import to_shape

    analise= nova_analise(sessao)
    a= criar_elemento(sessao, analise, 0, 0, ["x", "y", "z"])
    b= criar_elemento(sessao, analise, 8.4, 0, ["w"])
    revisao.juntar(sessao, a.id, b.id, "tecnica")
    sessao.refresh(a)
    assert abs(to_shape(a.geom).x - (LON + 2.1 / 84000)) < 1e-7


@precisa_bd
def test_juntar_recusa_casos_invalidos(sessao):
    analise, outra= nova_analise(sessao), nova_analise(sessao)
    a= criar_elemento(sessao, analise, 0, 0, ["x"])
    b= criar_elemento(sessao, analise, 4, 0, ["y"], categoria="sinal", classe="stop")
    c= criar_elemento(sessao, outra, 4, 0, ["z"])
    d= criar_elemento(sessao, analise, 4, 0, ["w"], estado="rejeitado")
    for destino, origem in ((a.id, a.id), (a.id, b.id), (a.id, c.id), (a.id, d.id)):
        with pytest.raises(ErroRevisao) as erro:
            revisao.juntar(sessao, destino, origem, "t")
        assert erro.value.codigo == 422
    with pytest.raises(ErroRevisao) as erro:
        revisao.juntar(sessao, a.id, 999999999, "t")
    assert erro.value.codigo == 404


@precisa_bd
def test_juntar_com_elemento_sem_posicao_herda_a_posicao(sessao):
    analise= nova_analise(sessao)
    sem= criar_elemento(sessao, analise, 0, 0, ["x"])
    sem.geom= None
    sem.metodo_geo= "sem_posicao"
    com= criar_elemento(sessao, analise, 5, 0, ["y"])
    sessao.flush()
    revisao.juntar(sessao, sem.id, com.id, "t")
    sessao.refresh(sem)
    assert sem.geom is not None
    assert sem.metodo_geo == "triangulacao"


@precisa_bd
def test_separar_cria_elemento_sem_posicao_com_as_fotografias_escolhidas(sessao):
    analise= nova_analise(sessao)
    elemento= criar_elemento(sessao, analise, 0, 0, ["x", "y", "z"])
    ids= [o.id for o in sessao.scalars(select(Observacao).where(Observacao.elemento_id == elemento.id).order_by(Observacao.id))]
    original, novo= revisao.separar(sessao, elemento.id, [ids[2]], "tecnica")
    assert original.n_observacoes == 2
    assert novo.n_observacoes == 1
    assert novo.geom is None
    assert novo.metodo_geo == "sem_posicao"
    assert novo.estado == "corrigido"
    assert novo.categoria == original.categoria
    assert [o.id for o in sessao.scalars(select(Observacao).where(Observacao.elemento_id == novo.id))] == [ids[2]]
    assert ("separado_de", str(original.id)) in correcoes(sessao, novo.id)
    assert any(campo == "separar" for campo, _ in correcoes(sessao, original.id))


@precisa_bd
def test_separar_recusa_casos_invalidos(sessao):
    analise= nova_analise(sessao)
    elemento= criar_elemento(sessao, analise, 0, 0, ["x", "y"])
    outro= criar_elemento(sessao, analise, 20, 0, ["z"])
    ids= [o.id for o in sessao.scalars(select(Observacao).where(Observacao.elemento_id == elemento.id))]
    alheia= sessao.scalar(select(Observacao.id).where(Observacao.elemento_id == outro.id))
    for pedido in ([], ids, [alheia]):
        with pytest.raises(ErroRevisao):
            revisao.separar(sessao, elemento.id, pedido, "t")


@precisa_bd
def test_duplicados_so_perto_sem_rejeitados_e_com_fotos_em_comum(sessao):
    analise= nova_analise(sessao)
    imagens= {}
    a= criar_elemento(sessao, analise, 0, 0, ["f1"], imagens=imagens)
    b= criar_elemento(sessao, analise, 2, 0, ["f2"], imagens=imagens)
    c= criar_elemento(sessao, analise, 0, 3.0, ["f1"], imagens=imagens)
    criar_elemento(sessao, analise, 50, 0, ["f3"], imagens=imagens)
    criar_elemento(sessao, analise, 1, 1, ["f4"], estado="rejeitado", imagens=imagens)
    criar_elemento(sessao, analise, 1, 1, ["f5"], categoria="sinal", classe="stop", imagens=imagens)
    pares= revisao.duplicados(sessao, analise.id, CRS, 4.0)
    por_par= {(p["a"], p["b"]): p for p in pares}
    assert set(por_par) == {(a.id, b.id), (a.id, c.id), (b.id, c.id)}
    assert por_par[(a.id, b.id)]["fotos_em_comum"] == 0
    assert por_par[(a.id, c.id)]["fotos_em_comum"] == 1
    assert por_par[(a.id, b.id)]["distancia_m"] < por_par[(a.id, c.id)]["distancia_m"]
    assert pares == sorted(pares, key=lambda p: (p["distancia_m"], p["a"], p["b"]))
    assert revisao.duplicados(sessao, analise.id, CRS, 0.5) == []


@precisa_bd
def test_api_juntar_separar_e_duplicados(cliente, sessao):
    analise= nova_analise(sessao)
    a= criar_elemento(sessao, analise, 0, 0, ["x", "y"])
    b= criar_elemento(sessao, analise, 2, 0, ["z"])
    pares= cliente.get(f"/analises/{analise.token}/duplicados").json()
    assert [(p["a"], p["b"]) for p in pares] == [(a.id, b.id)]
    assert cliente.get("/analises/inexistente/duplicados").status_code == 404
    resposta= cliente.post(f"/elementos/{a.id}/juntar", json={"origem": b.id, "autor": "tecnica"})
    assert resposta.status_code == 200
    assert resposta.json()["properties"]["n_observacoes"] == 3
    assert cliente.get(f"/elementos/{b.id}").json()["properties"]["estado"] == "rejeitado"
    assert cliente.get(f"/analises/{analise.token}/duplicados").json() == []
    observacoes= [o["id"] for o in cliente.get(f"/elementos/{a.id}").json()["properties"]["observacoes"]]
    separado= cliente.post(f"/elementos/{a.id}/separar", json={"observacoes": observacoes[:1], "autor": "tecnica"})
    assert separado.status_code == 200
    corpo= separado.json()
    assert corpo["original"]["properties"]["n_observacoes"] == 2
    assert corpo["novo"]["properties"]["n_observacoes"] == 1
    assert corpo["novo"]["geometry"] is None


@precisa_bd
def test_api_erros_de_validacao(cliente, sessao):
    analise= nova_analise(sessao)
    a= criar_elemento(sessao, analise, 0, 0, ["x"])
    assert cliente.post(f"/elementos/{a.id}/juntar", json={"origem": a.id, "autor": "t"}).status_code == 422
    assert cliente.post(f"/elementos/{a.id}/juntar", json={"origem": 999999999, "autor": "t"}).status_code == 404
    assert cliente.post(f"/elementos/{a.id}/juntar", json={"origem": a.id, "autor": ""}).status_code == 422
    assert cliente.post(f"/elementos/{a.id}/separar", json={"observacoes": [], "autor": "t"}).status_code == 422
    assert cliente.post("/elementos/999999999/separar", json={"observacoes": [1], "autor": "t"}).status_code == 404
