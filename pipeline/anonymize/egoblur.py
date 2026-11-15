from collections.abc import Callable, Sequence
from pathlib import Path

import cv2
import numpy as np

from pipeline.errors import ModeloEmFalta
from pipeline.models import ImageRecord

MODELOS= ("ego_blur_face.jit", "ego_blur_lp.jit")
LIMIAR_SCORE= 0.9
LIMIAR_NMS= 0.3

Detector= Callable[[np.ndarray], np.ndarray]


def blur_box(image: np.ndarray, box) -> None:
    altura, largura= image.shape[:2]
    x1, y1, x2, y2= (round(v) for v in box)
    x1, y1= max(x1, 0), max(y1, 0)
    x2, y2= min(x2, largura), min(y2, altura)
    if x2 <= x1 or y2 <= y1:
        return
    sigma= max(x2 - x1, y2 - y1) / 3
    image[y1:y2, x1:x2]= cv2.GaussianBlur(image[y1:y2, x1:x2], (0, 0), sigmaX=sigma)


class Anonymizer:
    def __init__(self, detectors: Sequence[Detector]):
        self.detectors= list(detectors)

    def __call__(self, image: np.ndarray) -> np.ndarray:
        saida= image.copy()
        for detetor in self.detectors:
            for caixa in detetor(image):
                blur_box(saida, caixa)
        return saida

    @classmethod
    def from_dir(cls, pasta: Path) -> "Anonymizer":
        em_falta= [nome for nome in MODELOS if not (pasta / nome).exists()]
        if em_falta:
            raise ModeloEmFalta(f"Modelos EgoBlur em falta em {pasta}: {', '.join(em_falta)}")
        return cls([_torchscript_detector(pasta / nome) for nome in MODELOS])


def _torchscript_detector(caminho: Path) -> Detector:
    import torch
    from torchvision.ops import nms

    dispositivo= "cuda" if torch.cuda.is_available() else "cpu"
    modelo= torch.jit.load(str(caminho), map_location="cpu").to(dispositivo).eval()

    def detetar(image: np.ndarray) -> np.ndarray:
        tensor= torch.from_numpy(np.transpose(image, (2, 0, 1)).copy()).to(dispositivo)
        with torch.no_grad():
            caixas, _, scores, _= modelo(tensor)
        manter= nms(caixas, scores, LIMIAR_NMS)
        caixas, scores= caixas[manter], scores[manter]
        return caixas[scores > LIMIAR_SCORE].cpu().numpy()

    return detetar


def caminho_anon(pasta: Path, registo: ImageRecord) -> Path:
    return pasta / f"{registo.fonte}_{registo.id_fonte}.jpg"


def save_anon(image: np.ndarray, pasta: Path, registo: ImageRecord) -> str:
    pasta.mkdir(parents=True, exist_ok=True)
    caminho= caminho_anon(pasta, registo)
    if not cv2.imwrite(str(caminho), image):
        raise OSError(f"Não foi possível gravar {caminho}")
    return str(caminho)
