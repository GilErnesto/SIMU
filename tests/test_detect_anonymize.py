from pathlib import Path

import numpy as np
import pytest

from pipeline.anonymize.egoblur import Anonymizer, save_anon
from pipeline.config import load_classes
from pipeline.detect.infer import Detector, resolve
from pipeline.errors import ModeloEmFalta
from pipeline.models import ImageRecord

CLASSES= load_classes(Path(__file__).parents[1] / "config" / "classes.yaml")


def test_sinal_confiante_mantem_classe():
    assert resolve("stop", 0.9, CLASSES) == ("sinal", "stop", False)


def test_sinal_pouco_confiante_cai_na_superclasse():
    assert resolve("limite_velocidade", 0.2, CLASSES) == ("sinal", "proibicao", True)
    assert resolve("stop", 0.2, CLASSES) == ("sinal", "cedencia", True)
    assert resolve("perigo", 0.2, CLASSES) == ("sinal", "outro", True)


def test_superclasse_nunca_e_obstruida():
    assert resolve("proibicao", 0.1, CLASSES) == ("sinal", "proibicao", False)


def test_classe_sem_limiar_nao_e_obstruida():
    assert resolve("luz", 0.1, CLASSES) == ("iluminacao", "luz", False)


def test_nome_do_yolo_candeeiro_passa_a_luz_geral():
    assert resolve("candeeiro", 0.9, CLASSES) == ("iluminacao", "luz", False)


def test_classe_fora_da_taxonomia_e_ignorada():
    assert resolve("banco", 0.9, CLASSES) is None


def test_pesos_em_falta(tmp_path):
    with pytest.raises(ModeloEmFalta, match="Pesos do detetor"):
        Detector.from_weights(tmp_path / "nada.pt", CLASSES)


def test_egoblur_em_falta(tmp_path):
    with pytest.raises(ModeloEmFalta, match="EgoBlur"):
        Anonymizer.from_dir(tmp_path)


def test_anonimizador_desfoca_so_dentro_da_caixa():
    rng= np.random.default_rng(0)
    imagem= rng.integers(0, 255, (100, 100, 3), dtype=np.uint8)
    anonimizador= Anonymizer([lambda _: np.array([[20, 20, 60, 60]])])
    saida= anonimizador(imagem)
    assert np.array_equal(saida[:, 70:], imagem[:, 70:])
    assert not np.array_equal(saida[20:60, 20:60], imagem[20:60, 20:60])
    assert saida[20:60, 20:60].std() < imagem[20:60, 20:60].std()
    assert saida is not imagem


class DetetorQueSoVeNaSegundaPassagem:
    def __init__(self):
        self.chamadas= 0

    def __call__(self, imagem):
        self.chamadas+= 1
        return np.array([[20, 20, 60, 60]]) if self.chamadas >= 2 else np.empty((0, 4))


def test_o_que_escapa_a_primeira_passagem_e_desfocado_na_segunda():
    rng= np.random.default_rng(1)
    imagem= rng.integers(0, 255, (100, 100, 3), dtype=np.uint8)
    detetor= DetetorQueSoVeNaSegundaPassagem()
    saida= Anonymizer([detetor])(imagem)
    assert detetor.chamadas == 2
    assert saida[20:60, 20:60].std() < imagem[20:60, 20:60].std()
    assert np.array_equal(saida[:, 70:], imagem[:, 70:])


def test_uma_so_passagem_deixa_escapar_o_que_so_a_segunda_ve():
    rng= np.random.default_rng(1)
    imagem= rng.integers(0, 255, (100, 100, 3), dtype=np.uint8)
    saida= Anonymizer([DetetorQueSoVeNaSegundaPassagem()], passagens=1)(imagem)
    assert np.array_equal(saida, imagem)


def test_a_segunda_passagem_corre_sobre_a_imagem_ja_desfocada():
    rng= np.random.default_rng(2)
    imagem= rng.integers(0, 255, (100, 100, 3), dtype=np.uint8)
    vistas= []

    def detetor(entrada):
        vistas.append(entrada.copy())
        return np.array([[20, 20, 60, 60]])

    Anonymizer([detetor])(imagem)
    assert np.array_equal(vistas[0], imagem)
    assert vistas[1][20:60, 20:60].std() < imagem[20:60, 20:60].std()


def test_caixa_fora_da_imagem_nao_falha():
    imagem= np.zeros((50, 50, 3), dtype=np.uint8)
    saida= Anonymizer([lambda _: np.array([[-10, -10, 200, 200], [60, 60, 70, 70]])])(imagem)
    assert saida.shape == imagem.shape


def test_save_anon_grava_na_pasta(tmp_path):
    registo= ImageRecord("mapillary", "123", "a", "l", "u", None, 0, 0, 0, "perspective", "x")
    caminho= save_anon(np.zeros((10, 10, 3), dtype=np.uint8), tmp_path / "anon", registo)
    assert Path(caminho).exists()
    assert Path(caminho).parent == tmp_path / "anon"
