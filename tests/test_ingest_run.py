from pathlib import Path

import pytest

from pipeline.ingest.mapillary import fetch_images, parse, tiles
from pipeline.run import main

CONFIG= Path(__file__).parents[1] / "config" / "municipio.yaml"

ITEM= {
    "id": "999",
    "computed_geometry": {"type": "Point", "coordinates": [-8.65, 40.64]},
    "computed_compass_angle": 123.5,
    "camera_type": "spherical",
    "captured_at": 1700000000000,
    "creator": {"username": "fotografo", "id": "7"},
    "thumb_2048_url": "https://exemplo.invalido/999.jpg",
}


class RespostaFalsa:
    def __init__(self, dados):
        self.dados= dados

    def raise_for_status(self):
        return None

    def json(self):
        return self.dados


class SessaoFalsa:
    def __init__(self, dados):
        self.dados= dados
        self.headers= {}
        self.pedidos= []

    def get(self, url, params=None, timeout=None):
        self.pedidos.append(params)
        return RespostaFalsa(self.dados)


def test_parse_guarda_atribuicao():
    registo= parse(ITEM)
    assert registo.autor == "fotografo"
    assert registo.licenca == "CC BY-SA 4.0"
    assert registo.url_origem.endswith("pKey=999")
    assert registo.heading == 123.5
    assert registo.camera_type == "spherical"
    assert registo.lon == -8.65


def test_parse_ignora_sem_posicao_corrigida():
    sem_geometria= {k: v for k, v in ITEM.items() if k != "computed_geometry"}
    assert parse(sem_geometria) is None


def test_tiles_cobrem_a_bbox():
    bbox= (-8.74, 40.54, -8.52, 40.72)
    caixas= list(tiles(bbox, 0.1))
    assert min(c[0] for c in caixas) == bbox[0]
    assert max(c[2] for c in caixas) == pytest.approx(bbox[2])
    assert max(c[3] for c in caixas) == pytest.approx(bbox[3])
    assert all((c[2] - c[0]) * (c[3] - c[1]) <= 0.01 + 1e-9 for c in caixas)


def test_fetch_junta_tiles_sem_duplicados():
    sessao= SessaoFalsa({"data": [ITEM]})
    imagens= fetch_images((-8.74, 40.54, -8.52, 40.72), "token", sessao)
    assert len(sessao.pedidos) > 1
    assert len(imagens) == 1
    assert sessao.headers["Authorization"] == "OAuth token"


def test_run_sem_token_falha_sem_gravar(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("MAPILLARY_TOKEN", "")
    monkeypatch.chdir(tmp_path)
    codigo= main(["--municipio", str(CONFIG)])
    assert codigo == 1
    assert "MAPILLARY_TOKEN" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_run_sem_modelos_falha_sem_gravar(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("MAPILLARY_TOKEN", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:1/x")
    monkeypatch.chdir(tmp_path)
    codigo= main(["--municipio", str(CONFIG)])
    assert codigo == 1
    assert "EgoBlur" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []
