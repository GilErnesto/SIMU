import io
import json

import cv2
import numpy as np
import pytest

from pipeline.detect.cabeca import Cabeca
from pipeline.errors import ErroPipeline
from training import tipos


def _item(classe, x0=0.4, y0=0.4, x1=0.5, y1=0.5):
    return {"valor": "v", "classe": classe, "caixa": [x0, y0, x1, y1]}


def test_divisao_e_estavel_e_ronda_um_quinto():
    ids= [f"id{n}" for n in range(2000)]
    assert tipos.divisao_de("abc") == tipos.divisao_de("abc")
    fracao= sum(tipos.divisao_de(i) == "val" for i in ids) / len(ids)
    assert 0.15 < fracao < 0.25


def test_recortes_com_margem_e_minimo():
    imagem= np.zeros((1000, 2000, 3), np.uint8)
    saida= tipos.recortes_de(imagem, [_item("stop"), _item("perigo", 0.5, 0.5, 0.505, 0.505)])
    assert [(n, c) for n, c, _ in saida] == [(0, "stop")]
    assert saida[0][2].shape[:2] == (130, 260)


def test_recortes_nao_saem_da_imagem():
    imagem= np.zeros((100, 100, 3), np.uint8)
    (_, _, recorte),= tipos.recortes_de(imagem, [_item("stop", -0.2, -0.2, 1.3, 1.3)], minimo=10)
    assert recorte.shape[:2] == (100, 100)


class _Anonimizador:
    def __init__(self):
        self.tamanhos= []

    def __call__(self, imagem):
        self.tamanhos.append(imagem.shape[:2])
        return np.zeros_like(imagem)


def test_recortar_anonimiza_grava_e_apaga_o_original(tmp_path):
    raw= tmp_path / "raw"
    raw.mkdir()
    cv2.imwrite(str(raw / "A.jpg"), np.full((3000, 4000, 3), 255, np.uint8))
    cv2.imwrite(str(raw / "B.jpg"), np.full((300, 400, 3), 255, np.uint8))
    ficheiro= tmp_path / "d.jsonl"
    ficheiro.write_text(
        json.dumps({"id_fonte": "A", "itens": [_item("stop"), _item("cedencia", 0.1, 0.1, 0.2, 0.2)]}) + "\n"
        + "{estragada\n"
        + json.dumps({"id_fonte": "B", "itens": [_item("stop", 0.1, 0.1, 0.12, 0.12)]}) + "\n"
        + json.dumps({"id_fonte": "SEM_FICHEIRO", "itens": [_item("stop")]}) + "\n"
    )
    anonimizador= _Anonimizador()
    contagem= tipos.recortar(ficheiro, raw, tmp_path / "s", anonimizador, io.StringIO())
    assert contagem == {"stop": 1, "cedencia": 1}
    assert anonimizador.tamanhos[0] == (1536, 2048)
    assert not (raw / "A.jpg").exists()
    assert not (raw / "B.jpg").exists()
    gravados= list((tmp_path / "s" / "recortes").glob("*/*/*.jpg"))
    assert len(gravados) == 2
    assert all(cv2.imread(str(g)).max() == 0 for g in gravados)


def test_avaliar_exatidao_e_por_classe():
    r= tipos.avaliar(["a", "a", "b", "b"], ["a", "b", "b", "b"])
    assert r["exatidao"] == pytest.approx(0.75)
    assert r["classes"]["a"]["precisao"] == pytest.approx(0.5)
    assert r["classes"]["a"]["recall"] == 1.0
    assert r["classes"]["b"]["recall"] == pytest.approx(2 / 3)


def _escrever_recortes(saida, divisao, classe, n, valor):
    pasta= saida / "recortes" / divisao / classe
    pasta.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        cv2.imwrite(str(pasta / f"{classe}{i}.jpg"), np.full((30, 30, 3), valor, np.uint8))


def test_treinar_tipos_guarda_a_cabeca_e_compara_com_o_zero_shot(tmp_path):
    saida= tmp_path / "s"
    for divisao, n in (("train", 40), ("val", 10)):
        _escrever_recortes(saida, divisao, "stop", n, 200)
        _escrever_recortes(saida, divisao, "perigo", n, 20)
        _escrever_recortes(saida, divisao, "raro", 3, 100)

    def incorporar(recortes):
        return np.array([[1.0, 0.0] if r.mean() > 100 else [0.0, 1.0] for r in recortes])

    def zero_shot(ficheiros):
        return ["stop"] * len(ficheiros)

    destino= tmp_path / "m" / "tipo.npz"
    relatorio= tipos.treinar_tipos(saida, incorporar, zero_shot, destino)
    assert relatorio["classes_usadas"] == ["perigo", "stop"]
    assert relatorio["cabeca"]["exatidao"] == 1.0
    assert relatorio["zero_shot"]["exatidao"] == pytest.approx(0.5)
    assert isinstance(Cabeca.carregar(destino), Cabeca)


def test_treinar_tipos_com_poucos_exemplos(tmp_path):
    _escrever_recortes(tmp_path, "train", "stop", 3, 100)
    with pytest.raises(ErroPipeline, match="Poucos exemplos"):
        tipos.treinar_tipos(tmp_path, lambda r: np.zeros((len(r), 2)), lambda f: [], tmp_path / "x.npz")
