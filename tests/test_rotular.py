import json

import pytest
from fastapi.testclient import TestClient

from training import rotular


def linha(id_fonte: str, confiancas: list[float]) -> str:
    return json.dumps(
        {
            "imagem": {"id_fonte": id_fonte, "width": 1000, "height": 500, "camera_type": "perspective", "lat": 40.6, "lon": -8.6},
            "deteccoes": [
                {"category": "iluminacao", "class_name": "luz", "bbox_xyxy": [10 + 50 * k, 20, 40 + 50 * k, 200], "confidence": c}
                for k, c in enumerate(confiancas)
            ],
        }
    )


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    (tmp_path / "lote_a").mkdir()
    (tmp_path / "imagens").mkdir()
    linhas= [linha(str(i), [0.9] if i % 2 else [0.2, 0.4, 0.8]) for i in range(1, 9)]
    (tmp_path / "lote_a" / "deteccoes.jsonl").write_text("\n".join(linhas), encoding="utf-8")
    for i in range(1, 9):
        (tmp_path / "imagens" / f"mapillary_{i}.jpg").write_bytes(b"jpg")
    monkeypatch.setattr(rotular, "BASE", tmp_path)
    return TestClient(rotular.app)


def test_lista_lotes(cliente):
    assert cliente.get("/api/lotes").json() == [{"lote": "lote_a", "feitas": 0}]


def test_fila_separa_aleatorias_e_incertas(cliente):
    fila= cliente.get("/api/lotes/lote_a/fila").json()
    ids= [i["id"] for i in fila]
    assert len(ids) == len(set(ids))
    aleatorias= {i["id"] for i in fila if i["origem"] == "aleatoria"}
    assert len(aleatorias) == 4
    for item in fila:
        if item["origem"] == "incerteza":
            assert item["id"] not in aleatorias


def test_com_todas_a_fila_traz_todas_as_imagens_do_lote(cliente, monkeypatch):
    monkeypatch.setattr(rotular, "TODAS", True)
    fila= cliente.get("/api/lotes/lote_a/fila").json()
    assert sorted(i["id"] for i in fila) == [str(i) for i in range(1, 9)]


def test_imagem_devolve_deteccoes_acima_do_limiar(cliente):
    dados= cliente.get("/api/lotes/lote_a/imagens/2").json()
    assert [d["confianca"] for d in dados["deteccoes"]] == [0.4, 0.8]
    assert dados["caixas"] is None


def test_gravar_e_reler(cliente):
    corpo= {"caixas": [{"bbox": [10, 20, 40, 200], "classe": "poste_luz", "origem": "modelo"}]}
    assert cliente.post("/api/lotes/lote_a/imagens/1", json=corpo).status_code == 200
    assert cliente.get("/api/lotes/lote_a/imagens/1").json()["caixas"][0]["classe"] == "poste_luz"
    feitos= [i for i in cliente.get("/api/lotes/lote_a/fila").json() if i["feito"]]
    assert [i["id"] for i in feitos] == ["1"]


def test_gravar_sem_caixas_guarda_lista_vazia_e_nao_repoe_as_do_modelo(cliente):
    assert cliente.post("/api/lotes/lote_a/imagens/2", json={"caixas": []}).status_code == 200
    assert cliente.get("/api/lotes/lote_a/imagens/2").json()["caixas"] == []


def test_gravar_ultima_versao_vence(cliente):
    caixa= {"bbox": [10, 20, 40, 200], "origem": "manual"}
    cliente.post("/api/lotes/lote_a/imagens/1", json={"caixas": [{**caixa, "classe": "poste_luz"}]})
    cliente.post("/api/lotes/lote_a/imagens/1", json={"caixas": [{**caixa, "classe": "candeeiro"}]})
    assert cliente.get("/api/lotes/lote_a/imagens/1").json()["caixas"][0]["classe"] == "candeeiro"


@pytest.mark.parametrize(
    "bbox", [[10, 20, 5, 200], [10, 20, 1100, 200], [-1, 20, 40, 200], [10, 20, 11, 200]]
)
def test_caixa_invalida_e_recusada(cliente, bbox):
    corpo= {"caixas": [{"bbox": bbox, "classe": "poste_luz", "origem": "manual"}]}
    assert cliente.post("/api/lotes/lote_a/imagens/1", json=corpo).status_code == 422


def test_classe_desconhecida_e_recusada(cliente):
    corpo= {"caixas": [{"bbox": [10, 20, 40, 200], "classe": "outra", "origem": "manual"}]}
    assert cliente.post("/api/lotes/lote_a/imagens/1", json=corpo).status_code == 422


@pytest.mark.parametrize("url", ["/api/lotes/..%2Fx/fila", "/api/lotes/inexistente/fila", "/api/lotes/lote_a/imagens/abc"])
def test_identificadores_invalidos(cliente, url):
    assert cliente.get(url).status_code == 404


def test_marca_auto_e_guardada_e_por_omissao_falsa(cliente):
    caixa= {"bbox": [10, 20, 40, 200], "classe": "poste_luz", "origem": "modelo"}
    corpo= {"caixas": [{**caixa, "auto": True}, {**caixa, "bbox": [60, 20, 90, 200]}]}
    cliente.post("/api/lotes/lote_a/imagens/1", json=corpo)
    guardadas= cliente.get("/api/lotes/lote_a/imagens/1").json()["caixas"]
    assert [c["auto"] for c in guardadas] == [True, False]


def linha_residuos(id_fonte: str) -> str:
    return json.dumps(
        {
            "imagem": {"id_fonte": id_fonte, "width": 1000, "height": 500, "camera_type": "perspective", "lat": 40.6, "lon": -8.6},
            "deteccoes": [
                {"category": "residuos", "class_name": "ilha_reciclagem", "bbox_xyxy": [10, 20, 90, 200], "confidence": 0.8},
                {"category": "iluminacao", "class_name": "luz", "bbox_xyxy": [300, 20, 330, 200], "confidence": 0.9},
            ],
        }
    )


@pytest.fixture
def cliente_residuos(tmp_path, monkeypatch):
    (tmp_path / "lote_r").mkdir()
    (tmp_path / "imagens").mkdir()
    (tmp_path / "lote_r" / "deteccoes.jsonl").write_text(linha_residuos("1"), encoding="utf-8")
    (tmp_path / "imagens" / "mapillary_1.jpg").write_bytes(b"jpg")
    monkeypatch.setattr(rotular, "BASE", tmp_path)
    monkeypatch.setattr(rotular, "CATEGORIA", "residuos")
    return TestClient(rotular.app)


def test_config_por_omissao_e_a_iluminacao(cliente):
    config= cliente.get("/api/config").json()
    assert config["categoria"] == "iluminacao"
    assert config["sugerida"] == "poste_luz"
    assert [c["id"] for c in config["classes"]] == ["poste_luz", "candeeiro", "nao_luz", "poste_eletrico"]


def test_config_dos_residuos(cliente_residuos):
    config= cliente_residuos.get("/api/config").json()
    assert config["categoria"] == "residuos"
    assert config["negativa"] == "nao_residuo"
    assert config["sugerida"] is None
    assert "ilha_reciclagem" in [c["id"] for c in config["classes"]]
    assert [c["id"] for c in config["classes"]][-1] == "residuo_outro"


def test_residuos_so_mostra_deteccoes_de_residuos_com_a_classe(cliente_residuos):
    dados= cliente_residuos.get("/api/lotes/lote_r/imagens/1").json()
    assert dados["deteccoes"] == [{"bbox": [10, 20, 90, 200], "confianca": 0.8, "classe": "ilha_reciclagem"}]


def test_residuos_aceita_as_suas_classes_e_grava_a_categoria(cliente_residuos, tmp_path):
    corpo= {"caixas": [
        {"bbox": [10, 20, 90, 200], "classe": "ilha_reciclagem", "origem": "modelo"},
        {"bbox": [400, 20, 450, 200], "classe": "nao_residuo", "origem": "manual"},
    ]}
    assert cliente_residuos.post("/api/lotes/lote_r/imagens/1", json=corpo).status_code == 200
    registo= json.loads((tmp_path / "rotulos" / "lote_r.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert registo["categoria"] == "residuos"
    assert [c["classe"] for c in registo["caixas"]] == ["ilha_reciclagem", "nao_residuo"]


def test_residuos_recusa_classes_de_luz(cliente_residuos):
    corpo= {"caixas": [{"bbox": [10, 20, 90, 200], "classe": "poste_luz", "origem": "manual"}]}
    assert cliente_residuos.post("/api/lotes/lote_r/imagens/1", json=corpo).status_code == 422
