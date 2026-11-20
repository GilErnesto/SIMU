import random

import numpy as np

from pipeline.detect.cabeca import Cabeca
from training.tipos_web import aumentar, misturar


def _sinal():
    rgba= np.zeros((120, 120, 4), np.uint8)
    rgba[20:100, 20:100]= (0, 0, 255, 255)
    return rgba


def test_aumentar_devolve_um_recorte_bgr_pequeno_e_reprodutivel():
    fundos= [np.full((300, 400, 3), 128, np.uint8)]
    for semente in range(30):
        recorte= aumentar(random.Random(semente), _sinal(), fundos)
        assert recorte.ndim == 3 and recorte.shape[2] == 3
        assert recorte.dtype == np.uint8
        assert max(recorte.shape[:2]) <= 140
    a= aumentar(random.Random(3), _sinal(), fundos)
    b= aumentar(random.Random(3), _sinal(), fundos)
    assert np.array_equal(a, b)


def test_misturar_junta_as_classes_e_da_peso_as_duas():
    antiga= Cabeca(["stop", "perigo"], np.array([[2.0, 0.0], [0.0, 2.0]]), np.zeros(2))
    nova= Cabeca(["perigo", "prescricao", "stop"], np.array([[0.0, 4.0], [1.0, 1.0], [4.0, 0.0]]), np.zeros(3))
    mista= misturar(antiga, nova, peso=0.5, penalizacao=2.0)
    assert mista.classes == ["perigo", "prescricao", "stop"]
    assert mista.coef[2].tolist() == [3.0, 0.0]
    assert mista.intercepto[1] == -1.0
    assert mista.prever(np.array([[1.0, 0.0]]))[0][0] == "stop"
