import io
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.deps import get_classes, get_municipio, get_session
from backend.main import app
from pipeline.catalog import analises
from pipeline.catalog.write import ensure_schema, write_catalog
from pipeline.config import load_classes
from pipeline.models import Detection, Element, ImageRecord, Observation

RAIZ= Path(__file__).parents[1]
CLASSES= load_classes(RAIZ / "config" / "classes.yaml")
URL_BD= os.environ.get("TEST_DATABASE_URL")
pytestmark= pytest.mark.skipif(not URL_BD, reason="TEST_DATABASE_URL não definido")
MP4= b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64
GPX= b'<?xml version="1.0"?><gpx version="1.1"><trk><trkseg></trkseg></trk></gpx>'


@pytest.fixture(autouse=True)
def ambiente(monkeypatch, tmp_path):
    monkeypatch.setenv("MUNICIPIO_YAML", str(RAIZ / "config" / "municipio.yaml"))
    monkeypatch.setenv("ANON_DIR", str(tmp_path / "anon"))
    monkeypatch.setenv("RAW_DIR", str(tmp_path / "raw"))
    (tmp_path / "raw").mkdir()
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


def _jpeg():
    saida= io.BytesIO()
    Image.new("RGB", (32, 32), (100, 100, 100)).save(saida, format="JPEG")
    return saida.getvalue()


def _enviar(cliente, ficheiros, **dados):
    envio= [("ficheiros", (nome, conteudo, "application/octet-stream")) for nome, conteudo in ficheiros]
    return cliente.post("/analises", files=envio, data=dados)


def test_envio_cria_analise_na_fila_e_guarda_o_original_so_em_raw(cliente, sessao, tmp_path):
    resposta= _enviar(cliente, [("a.jpg", _jpeg()), ("t.gpx", GPX)], nome="Rua teste")
    assert resposta.status_code == 201
    dados= resposta.json()
    assert dados["url"] == f"/a/{dados['token']}"
    assert dados["estado"] == "na_fila"
    pasta= tmp_path / "raw" / dados["token"]
    assert sorted(p.name for p in pasta.iterdir()) == ["0001_a.jpg", "0002_t.gpx"]
    detalhe= cliente.get(f"/analises/{dados['token']}").json()
    assert detalhe["nome"] == "Rua teste"
    assert detalhe["estado"] == "na_fila"
    assert not (tmp_path / "anon").exists()


def test_nome_vazio_fica_com_um_nome_por_omissao(cliente, sessao):
    token= _enviar(cliente, [("a.jpg", _jpeg())]).json()["token"]
    assert cliente.get(f"/analises/{token}").json()["nome"] == "Análise sem nome"


def test_video_sem_gpx_avisa(cliente, sessao):
    token= _enviar(cliente, [("v.mp4", MP4)]).json()["token"]
    avisos= cliente.get(f"/analises/{token}").json()["avisos"]
    assert any("sem ficheiro GPX" in a for a in avisos)


def test_tipo_nao_suportado_e_conteudo_falso_sao_ignorados(cliente, sessao, tmp_path):
    resposta= _enviar(
        cliente, [("a.jpg", _jpeg()), ("b.exe", b"MZ"), ("falsa.jpg", b"isto nao e uma imagem")]
    )
    assert resposta.status_code == 201
    token= resposta.json()["token"]
    avisos= cliente.get(f"/analises/{token}").json()["avisos"]
    assert any("b.exe" in a and "não suportado" in a for a in avisos)
    assert any("falsa.jpg" in a and "não corresponde" in a for a in avisos)
    assert [p.name for p in (tmp_path / "raw" / token).iterdir()] == ["0001_a.jpg"]


def test_sem_nada_valido_recusa_e_nao_deixa_lixo(cliente, sessao, tmp_path):
    resposta= _enviar(cliente, [("falsa.jpg", b"texto"), ("t.gpx", GPX)])
    assert resposta.status_code == 400
    assert list((tmp_path / "raw").iterdir()) == []


def test_limite_de_tamanho(cliente, sessao, tmp_path, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "0")
    resposta= _enviar(cliente, [("a.jpg", _jpeg())])
    assert resposta.status_code == 413
    assert list((tmp_path / "raw").iterdir()) == []


def test_fps_invalido(cliente, sessao):
    assert _enviar(cliente, [("a.jpg", _jpeg())], fps="50").status_code == 422


def test_nome_de_ficheiro_perigoso_nao_sai_da_pasta(cliente, sessao, tmp_path):
    token= _enviar(cliente, [("../../../fora.jpg", _jpeg())]).json()["token"]
    assert [p.name for p in (tmp_path / "raw" / token).iterdir()] == ["0001_fora.jpg"]
    assert not (tmp_path.parent / "fora.jpg").exists()


def test_lista_e_detalhe(cliente, sessao):
    primeiro= _enviar(cliente, [("a.jpg", _jpeg())], nome="Primeira").json()["token"]
    segundo= _enviar(cliente, [("b.jpg", _jpeg())], nome="Segunda").json()["token"]
    lista= cliente.get("/analises").json()
    nomes= [a["nome"] for a in lista]
    assert nomes.index("Segunda") < nomes.index("Primeira")
    assert {primeiro, segundo} <= {a["token"] for a in lista}
    assert cliente.get("/analises/nao-existe").status_code == 404


def _imagem(identificador):
    return ImageRecord(
        "upload", identificador, "Utilizador", "Dados do utilizador", "",
        datetime(2026, 1, 1, tzinfo=UTC), -8.65, 40.64, 0.0, "perspective", "x",
        width=1000, height=800, caminho_anon=f"data/anon/{identificador}.jpg",
    )


def _elemento(registo, lon, lat):
    deteccao= Detection(registo.id, "iluminacao", "candeeiro", (1, 2, 3, 4), 0.8, False)
    return Element("iluminacao", "candeeiro", lon, lat, False, "monocular", [Observation(deteccao, registo, 1.0)])


def test_elementos_e_exportacoes_por_analise(cliente, sessao):
    a= analises.criar(sessao, "A")
    b= analises.criar(sessao, "B")
    ia, ib= _imagem("a-1"), _imagem("b-1")
    write_catalog(sessao, CLASSES, [ia], [_elemento(ia, -8.65, 40.64)], analise_id=a.id)
    write_catalog(sessao, CLASSES, [ib], [_elemento(ib, -8.60, 40.60)], analise_id=b.id)
    so_a= cliente.get(f"/elementos?analise={a.token}").json()["features"]
    assert len(so_a) == 1
    assert so_a[0]["geometry"]["coordinates"][0] == pytest.approx(-8.65)
    assert len(cliente.get(f"/elementos?analise={b.token}").json()["features"]) == 1
    exportado= cliente.get(f"/export.geojson?analise={a.token}").json()["features"]
    assert len(exportado) == 1
    assert cliente.get(f"/export.csv?analise={b.token}").text.count("\n") == 2
    assert len(cliente.get("/elementos").json()["features"]) >= 2


def test_analise_desconhecida_nos_elementos(cliente, sessao):
    assert cliente.get("/elementos?analise=nao-existe").status_code == 404
    assert cliente.get("/export.geojson?analise=nao-existe").status_code == 404
    assert cliente.get("/export.csv?analise=nao-existe").status_code == 404


def test_filtro_por_classe(cliente, sessao):
    a= analises.criar(sessao, "A")
    ia= _imagem("c-1")
    luz= _elemento(ia, -8.65, 40.64)
    write_catalog(sessao, CLASSES, [ia], [luz], analise_id=a.id)
    assert len(cliente.get(f"/elementos?analise={a.token}&classe=candeeiro").json()["features"]) == 1
    assert cliente.get(f"/elementos?analise={a.token}&classe=stop").json()["features"] == []
    assert len(cliente.get(f"/export.geojson?analise={a.token}&classe=candeeiro").json()["features"]) == 1
    assert cliente.get(f"/export.csv?analise={a.token}&classe=stop").text.count("\n") == 1


def _analise_com_dados(sessao, nome, identificador, tmp_path, lon= -8.65, lat= 40.64):
    analise= analises.criar(sessao, nome)
    registo= _imagem(identificador)
    anon= tmp_path / "anon"
    anon.mkdir(exist_ok=True)
    (anon / f"{identificador}.jpg").write_bytes(_jpeg())
    write_catalog(sessao, CLASSES, [registo], [_elemento(registo, lon, lat)], analise_id=analise.id)
    analises.atualizar_contagens(sessao, analise)
    return analise


def _contagens(sessao, analise_id):
    from sqlalchemy import func, select

    from pipeline.catalog.write import Correcao, Elemento, Imagem, Observacao

    ids= select(Elemento.id).where(Elemento.analise_id == analise_id)
    return {
        "elementos": sessao.scalar(select(func.count(Elemento.id)).where(Elemento.analise_id == analise_id)),
        "imagens": sessao.scalar(select(func.count(Imagem.id)).where(Imagem.analise_id == analise_id)),
        "observacoes": sessao.scalar(select(func.count(Observacao.id)).where(Observacao.elemento_id.in_(ids))),
        "correcoes": sessao.scalar(select(func.count(Correcao.id)).where(Correcao.elemento_id.in_(ids))),
    }


def test_apagar_analise_limpa_a_base_e_os_ficheiros(cliente, sessao, tmp_path):
    a= _analise_com_dados(sessao, "A", "del-a", tmp_path)
    b= _analise_com_dados(sessao, "B", "del-b", tmp_path, lon= -8.60, lat= 40.60)
    elemento_id= cliente.get(f"/elementos?analise={a.token}").json()["features"][0]["properties"]["id"]
    assert cliente.patch(f"/elementos/{elemento_id}", json={"estado": "validado", "autor": "Técnico"}).status_code == 200
    assert _contagens(sessao, a.id) == {"elementos": 1, "imagens": 1, "observacoes": 1, "correcoes": 1}
    pasta_raw= tmp_path / "raw" / a.token
    pasta_raw.mkdir()
    (pasta_raw / "foto.jpg").write_bytes(b"x")
    resposta= cliente.delete(f"/analises/{a.token}")
    assert resposta.status_code == 200
    assert resposta.json() == {"elementos": 1, "imagens": 1, "ficheiros_por_apagar": 0}
    assert _contagens(sessao, a.id) == {"elementos": 0, "imagens": 0, "observacoes": 0, "correcoes": 0}
    assert cliente.get(f"/analises/{a.token}").status_code == 404
    assert not (tmp_path / "anon" / "del-a.jpg").exists()
    assert not pasta_raw.exists()
    assert (tmp_path / "anon" / "del-b.jpg").exists()
    assert _contagens(sessao, b.id) == {"elementos": 1, "imagens": 1, "observacoes": 1, "correcoes": 0}
    assert cliente.get(f"/analises/{b.token}").status_code == 200
    assert a.token not in {x["token"] for x in cliente.get("/analises").json()}


def test_apagar_analise_desconhecida(cliente, sessao):
    assert cliente.delete("/analises/nao-existe").status_code == 404


def test_nao_se_apaga_uma_analise_a_ser_processada(cliente, sessao, tmp_path):
    a= _analise_com_dados(sessao, "A", "proc-a", tmp_path)
    a.estado= "a_processar"
    sessao.commit()
    resposta= cliente.delete(f"/analises/{a.token}")
    assert resposta.status_code == 409
    assert "processada" in resposta.json()["detail"]
    assert _contagens(sessao, a.id)["elementos"] == 1
    assert (tmp_path / "anon" / "proc-a.jpg").exists()


def test_apagar_analise_na_fila_remove_os_ficheiros_enviados(cliente, sessao, tmp_path):
    token= _enviar(cliente, [("a.jpg", _jpeg())], nome="Na fila").json()["token"]
    assert (tmp_path / "raw" / token).is_dir()
    assert cliente.delete(f"/analises/{token}").status_code == 200
    assert not (tmp_path / "raw" / token).exists()
    assert cliente.get(f"/analises/{token}").status_code == 404


def test_apagar_so_toca_em_ficheiros_da_pasta_anonimizada(cliente, sessao, tmp_path):
    from sqlalchemy import update

    from pipeline.catalog.write import Imagem

    a= _analise_com_dados(sessao, "A", "seg-a", tmp_path)
    fora= tmp_path / "fora.jpg"
    fora.write_bytes(b"nao apagar")
    sessao.execute(update(Imagem).where(Imagem.analise_id == a.id).values(caminho_anon="../fora.jpg"))
    sessao.commit()
    assert cliente.delete(f"/analises/{a.token}").status_code == 200
    assert fora.exists()


def test_apagar_conta_os_ficheiros_que_nao_conseguiu_remover(cliente, sessao, tmp_path, monkeypatch):
    a= _analise_com_dados(sessao, "A", "falha-a", tmp_path)

    def recusar(self, *args, **kwargs):
        raise PermissionError("só de leitura")

    monkeypatch.setattr(Path, "unlink", recusar)
    resposta= cliente.delete(f"/analises/{a.token}")
    monkeypatch.undo()
    assert resposta.status_code == 200
    assert resposta.json()["ficheiros_por_apagar"] == 1
    assert cliente.get(f"/analises/{a.token}").status_code == 404
