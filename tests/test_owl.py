from pathlib import Path

import numpy as np
import pytest

from pipeline.config import load_classes

torch= pytest.importorskip("torch")
pytest.importorskip("torchvision")

from pipeline.detect.owl import OwlDetector

CLASSES= load_classes(Path(__file__).parents[1] / "config" / "classes.yaml")


class Entradas(dict):
    def to(self, _):
        return self


class ProcessadorFalso:
    def __init__(self, resultado):
        self.resultado= resultado
        self.visto= None
        self.image_processor= self

    def __call__(self, text, images, return_tensors):
        self.visto= (text, images.shape)
        return Entradas()

    def post_process_object_detection(self, outputs, threshold, target_sizes):
        self.alvo= target_sizes.tolist()
        return [self.resultado]


class ModeloFalso:
    def __call__(self, **_):
        return object()


def _detetor(resultado):
    return OwlDetector(ProcessadorFalso(resultado), ModeloFalso(), CLASSES)


def _resultado(caixas, scores, etiquetas):
    return {
        "boxes": torch.tensor(caixas, dtype=torch.float32),
        "scores": torch.tensor(scores, dtype=torch.float32),
        "labels": torch.tensor(etiquetas),
    }


def test_consultas_cobrem_a_taxonomia():
    detetor= _detetor(_resultado([], [], []))
    classes= {classe for _, classe in detetor.alvos}
    assert {"outro", "semaforo", "candeeiro", "contentor", "papeleira"} <= classes
    assert "stop" not in classes
    assert len(detetor.alvos) == len(detetor.textos)


def test_mapeia_etiqueta_para_classe():
    detetor= _detetor(_resultado([[10, 20, 50, 80]], [0.9], [0]))
    detecoes= detetor.detect("img", np.zeros((100, 200, 3), dtype=np.uint8))
    assert len(detecoes) == 1
    assert (detecoes[0].category, detecoes[0].class_name) == detetor.alvos[0]
    assert detecoes[0].bbox_xyxy == (10, 20, 50, 80)
    assert detecoes[0].obstruido is False
    assert detecoes[0].image_id == "img"


def test_alvo_do_pos_processamento_e_quadrado():
    detetor= _detetor(_resultado([], [], []))
    detetor.detect("img", np.zeros((100, 200, 3), dtype=np.uint8))
    assert detetor.processor.alvo == [[200, 200]]


def test_caixa_e_cortada_a_imagem():
    detetor= _detetor(_resultado([[-5, -5, 300, 150]], [0.9], [0]))
    caixa= detetor.detect("img", np.zeros((100, 200, 3), dtype=np.uint8))[0].bbox_xyxy
    assert caixa == (0, 0, 200, 100)


def test_caixa_fora_da_imagem_e_descartada():
    detetor= _detetor(_resultado([[250, 120, 300, 150]], [0.9], [0]))
    assert detetor.detect("img", np.zeros((100, 200, 3), dtype=np.uint8)) == []


def test_nms_remove_sobreposicao_da_mesma_classe():
    detetor= _detetor(_resultado([[10, 10, 60, 60], [12, 12, 62, 62]], [0.9, 0.5], [0, 0]))
    assert len(detetor.detect("img", np.zeros((100, 200, 3), dtype=np.uint8))) == 1


def test_sem_resultados():
    detetor= _detetor(_resultado([], [], []))
    assert detetor.detect("img", np.zeros((100, 200, 3), dtype=np.uint8)) == []


def test_nms_e_por_categoria():
    detetor= _detetor(_resultado([[10, 10, 60, 60], [12, 12, 62, 62]], [0.9, 0.5], [0, 1]))
    assert detetor.alvos[0][0] == detetor.alvos[1][0]
    assert len(detetor.detect("img", np.zeros((100, 200, 3), dtype=np.uint8))) == 1
