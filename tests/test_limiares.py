import dataclasses
from pathlib import Path

from pipeline.config import load_classes
from pipeline.detect.infer import Limiares
from pipeline.models import Detection

CLASSES= load_classes(Path(__file__).parents[1] / "config" / "classes.yaml")


class _Fixo:
    def __init__(self, deteccoes):
        self.deteccoes= deteccoes

    def detect(self, image_id, image):
        return self.deteccoes


def _com_limiares(**limiares):
    categorias= {
        nome: dataclasses.replace(categoria, limiar_detecao=limiares.get(nome, 0.0))
        for nome, categoria in CLASSES.categorias.items()
    }
    return dataclasses.replace(CLASSES, categorias=categorias)


def test_limiares_por_categoria():
    deteccoes= [
        Detection("i", "sinal", "stop", (0, 0, 1, 1), 0.45, False),
        Detection("i", "sinal", "stop", (0, 0, 1, 1), 0.55, False),
        Detection("i", "iluminacao", "candeeiro", (0, 0, 1, 1), 0.45, False),
    ]
    ficam= Limiares(_Fixo(deteccoes), _com_limiares(sinal=0.5, iluminacao=0.4)).detect("i", None)
    assert [d.confidence for d in ficam] == [0.55, 0.45]


def test_limiar_por_omissao_nao_filtra():
    assert all(c.limiar_detecao >= 0 for c in CLASSES.categorias.values())
    deteccao= Detection("i", "residuos", "contentor", (0, 0, 1, 1), 0.01, False)
    assert Limiares(_Fixo([deteccao]), _com_limiares()).detect("i", None) == [deteccao]
