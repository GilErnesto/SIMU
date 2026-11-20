"""Detection on overlapping native-resolution tiles, for small signs in big photos."""

from pipeline.detect.panorama import nms
from pipeline.models import Detection

LADO_LADRILHO= 1024
PASSO_LADRILHO= 768
MINIMO_PARA_LADRILHAR= 1300


def _inicios(total: int, lado: int, passo: int) -> list[int]:
    if total <= lado:
        return [0]
    return [*range(0, total - lado, passo), total - lado]


def detetar_com_ladrilhos(detetor, nome: str, imagem) -> list:
    """Whole image plus overlapping native-resolution tiles, merged.

    The detector was trained at about 1024 px, so on a 2048 px photo small signs end up tiny.
    Tiles keep them at full size; duplicates between tiles and the whole image are merged.
    """
    altura, largura= imagem.shape[:2]
    deteccoes= list(detetor.detect(nome, imagem))
    if max(altura, largura) < MINIMO_PARA_LADRILHAR:
        return deteccoes
    for y in _inicios(altura, LADO_LADRILHO, PASSO_LADRILHO):
        for x in _inicios(largura, LADO_LADRILHO, PASSO_LADRILHO):
            for d in detetor.detect(nome, imagem[y : y + LADO_LADRILHO, x : x + LADO_LADRILHO]):
                x1, y1, x2, y2= d.bbox_xyxy
                caixa= (x1 + x, y1 + y, x2 + x, y2 + y)
                deteccoes.append(
                    Detection(nome, d.category, d.class_name, caixa, d.confidence, d.obstruido)
                )
    return nms(deteccoes, 10**9)



class Ladrilhos:
    """Wraps a detector so big perspective photos are also searched tile by tile."""

    def __init__(self, detetor):
        self.detetor= detetor

    def detect(self, image_id: str, image) -> list[Detection]:
        return detetar_com_ladrilhos(self.detetor, image_id, image)
