from pathlib import Path

import numpy as np

from pipeline.config import Classes
from pipeline.errors import ModeloEmFalta
from pipeline.models import Detection


def resolve(nome: str, confianca: float, classes: Classes) -> tuple[str, str, bool] | None:
    categoria= classes.categoria_de(nome)
    if categoria is None:
        return None
    limiar= categoria.limiar_especifica
    genericas= set(categoria.superclasse.values()) | {categoria.superclasse_padrao}
    if limiar is None or nome in genericas or confianca >= limiar:
        return categoria.nome, nome, False
    destino= categoria.superclasse.get(nome, categoria.superclasse_padrao) or nome
    return categoria.nome, destino, True


class Detector:
    def __init__(self, modelo, classes: Classes):
        self.modelo= modelo
        self.classes= classes

    @classmethod
    def from_weights(cls, pesos: Path, classes: Classes) -> "Detector":
        if not pesos.exists():
            raise ModeloEmFalta(f"Pesos do detetor em falta: {pesos}")
        from ultralytics import YOLO

        return cls(YOLO(str(pesos)), classes)

    def detect(self, image_id: str, image: np.ndarray) -> list[Detection]:
        resultado= self.modelo(image, verbose=False)[0]
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
