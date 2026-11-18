from pathlib import Path

import numpy as np

from pipeline.config import Classes
from pipeline.errors import ModeloEmFalta
from pipeline.models import Detection


def resolve(nome: str, confianca: float, classes: Classes) -> tuple[str, str, bool] | None:
    categoria= classes.categoria_de(nome)
    if categoria is None:
        return None
    nome= categoria.alias.get(nome, nome)
    limiar= categoria.limiar_especifica
    genericas= set(categoria.superclasse.values()) | {categoria.superclasse_padrao}
    if limiar is None or nome in genericas or confianca >= limiar:
        return categoria.nome, nome, False
    destino= categoria.superclasse.get(nome, categoria.superclasse_padrao) or nome
    return categoria.nome, destino, True


class Limiares:
    def __init__(self, detetor, classes: Classes):
        self.detetor= detetor
        self.classes= classes

    def detect(self, image_id: str, image: np.ndarray) -> list[Detection]:
        return [
            d
            for d in self.detetor.detect(image_id, image)
            if d.confidence >= self.classes.categorias[d.category].limiar_detecao
        ]


class Detector:
    def __init__(self, modelo, classes: Classes, limiar: float= 0.25):
        self.modelo= modelo
        self.classes= classes
        self.limiar= limiar

    @classmethod
    def from_weights(cls, pesos: Path, classes: Classes, limiar: float= 0.25) -> "Detector":
        if not pesos.exists():
            raise ModeloEmFalta(f"Pesos do detetor em falta: {pesos}")
        from ultralytics import YOLO

        return cls(YOLO(str(pesos)), classes, limiar)

    def detect(self, image_id: str, image: np.ndarray) -> list[Detection]:
        resultado= self.modelo(image, verbose=False, conf=self.limiar)[0]
        nomes= resultado.names
        caixas= resultado.boxes
        detecoes= []
        for caixa, conf, idx in zip(
            caixas.xyxy.tolist(), caixas.conf.tolist(), caixas.cls.tolist()
        ):
            decisao= resolve(nomes[int(idx)], conf, self.classes)
            if decisao is None:
                continue
            categoria, classe, obstruido= decisao
            detecoes.append(Detection(image_id, categoria, classe, tuple(caixa), conf, obstruido))
        return detecoes
