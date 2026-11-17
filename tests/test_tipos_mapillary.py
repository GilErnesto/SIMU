import io
import json

import pytest

from pipeline.models import ImageRecord
from training.datasets import tipos_mapillary as tm

CEDENCIA= "GiV4AgoGbXB5LW9yKIAgEhYYAwgBIhAJjCCqGxoAkgP6AQAAkQMP"


def _registo(id_fonte, lon=-8.66, lat=40.63, camera="perspective"):
    return ImageRecord("mapillary", id_fonte, "Ana", "CC BY-SA 4.0", f"u/{id_fonte}", None, lon, lat, 0.0, camera, f"https://img/{id_fonte}")


def test_candidatas_tira_panoramas_e_zonas_excluidas():
    excluidas= [(-8.66, 40.63, -8.65, 40.64)]
    registos= [
        _registo("dentro", -8.655, 40.635),
        _registo("margem", -8.6605, 40.63),
        _registo("fora", -8.68, 40.62),
        _registo("pano", -8.68, 40.62, "spherical"),
    ]
    assert [r.id_fonte for r in tm.candidatas(registos, excluidas, margem=0.001)] == ["fora"]


def test_candidatas_e_estavel_com_a_mesma_semente():
    registos= [_registo(str(n), -8.69, 40.62) for n in range(20)]
    assert [r.id_fonte for r in tm.candidatas(registos, [], semente=1)] == [r.id_fonte for r in tm.candidatas(registos[::-1], [], semente=1)]


def test_itens_de_sinais_so_guarda_sinais_com_geometria_valida():
    deteccoes= [
        {"value": "regulatory--yield--g1", "geometry": CEDENCIA},
        {"value": "object--traffic-light--general-upright", "geometry": CEDENCIA},
        {"value": "construction--barrier--curb", "geometry": CEDENCIA},
        {"value": "regulatory--stop--g1", "geometry": "isto não é base64!"},
        {"value": "regulatory--stop--g1"},
        {"value": "complementary--distance--g1", "geometry": CEDENCIA},
    ]
    itens= tm.itens_de_sinais(deteccoes)
    assert [i["classe"] for i in itens] == ["cedencia", "semaforo"]
    assert itens[0]["valor"] == "regulatory--yield--g1"
    assert itens[0]["caixa"][0] == pytest.approx(0.50146, abs=1e-4)


class _Resposta:
    def __init__(self, dados=None, conteudo=b"", estado=200):
        self.status_code= estado
        self._dados= dados
        self.content= conteudo

    def json(self):
        return {"data": self._dados}


class _Sessao:
    def __init__(self, deteccoes_por_imagem):
        self.deteccoes= deteccoes_por_imagem
        self.pedidos= []

    def get(self, url, timeout=None, params=None):
        self.pedidos.append(url)
        if "/detections" in url:
            id_= url.split("/")[-2]
            return _Resposta(self.deteccoes.get(id_, []))
        return _Resposta(conteudo=b"JPEG-" + url.encode())


def test_processar_so_descarrega_a_imagem_quando_ha_sinais(tmp_path):
    sessao= _Sessao({"com": [{"value": "regulatory--stop--g1", "geometry": CEDENCIA}], "sem": []})
    assert tm.processar(_registo("sem"), sessao, tmp_path) is None
    assert not (tmp_path / "sem.jpg").exists()
    resultado= tm.processar(_registo("com"), sessao, tmp_path)
    assert resultado["id_fonte"] == "com"
    assert resultado["licenca"] == "CC BY-SA 4.0"
    assert resultado["itens"][0]["classe"] == "stop"
    assert (tmp_path / "com.jpg").read_bytes().startswith(b"JPEG-")
    assert sum("/detections" not in u for u in sessao.pedidos) == 1


def test_recolher_para_no_alvo_e_retoma_sem_repetir(tmp_path):
    deteccoes= {str(n): [{"value": "regulatory--stop--g1", "geometry": CEDENCIA}] for n in range(30)}
    sessao= _Sessao(deteccoes)
    registos= [_registo(str(n)) for n in range(30)]
    ficheiro= tmp_path / "d.jsonl"
    consultadas, recortes= tm.recolher(registos, sessao, tmp_path / "raw", ficheiro, 10, 100, 2, io.StringIO())
    assert recortes >= 10
    assert consultadas < 30
    feitas, total= tm.ja_feitas(ficheiro)
    assert total == recortes
    pedidos_antes= len(sessao.pedidos)
    _, recortes2= tm.recolher(registos, sessao, tmp_path / "raw", ficheiro, 14, 100, 2, io.StringIO())
    assert recortes2 >= 14
    novos= [u for u in sessao.pedidos[pedidos_antes:] if "/detections" in u]
    assert all(u.split("/")[-2] not in feitas for u in novos)


def test_ja_feitas_ignora_linhas_estragadas(tmp_path):
    ficheiro= tmp_path / "d.jsonl"
    ficheiro.write_text(json.dumps({"id_fonte": "a", "itens": [1, 2]}) + "\n{estragada\n")
    assert tm.ja_feitas(ficheiro) == ({"a"}, 2)
