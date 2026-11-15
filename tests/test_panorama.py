import numpy as np
import pytest

from pipeline.anonymize.egoblur import save_anon
from pipeline.detect.panorama import LADO_VISTA, detect_panorama, nms, views
from pipeline.geolocate.bearing import object_bearing
from pipeline.models import Detection, ImageRecord
from pipeline.run import processar

LARGURA= 960
ALTURA= 480


def _pinta(imagem: np.ndarray, x: int, y: int, lado: int) -> None:
    for dx in range(-lado // 2, lado // 2):
        for dy in range(-lado // 2, lado // 2):
            imagem[(y + dy) % ALTURA, (x + dx) % LARGURA]= 255


def _panorama(lon: float, lat: float, lado: int= 48) -> np.ndarray:
    imagem= np.zeros((ALTURA, LARGURA, 3), np.uint8)
    _pinta(
        imagem,
        round((lon / 360 + 0.5) * LARGURA),
        round((0.5 - lat / 180) * ALTURA),
        lado,
    )
    return imagem


def _caixa_do_marcador(vista: np.ndarray):
    mascara= vista[:, :, 0] > 128
    linhas= np.flatnonzero(mascara.any(axis=1))
    colunas= np.flatnonzero(mascara.any(axis=0))
    if linhas.size == 0:
        return None
    return (float(colunas[0]), float(linhas[0]), float(colunas[-1] + 1), float(linhas[-1] + 1))


class DetetorDeMarcador:
    def __init__(self, classe: str= "stop"):
        self.classe= classe
        self.chamadas= 0

    def detect(self, image_id: str, image: np.ndarray) -> list[Detection]:
        self.chamadas += 1
        caixa= _caixa_do_marcador(image)
        if caixa is None:
            return []
        return [Detection(image_id, "sinal", self.classe, caixa, 0.9, False)]


def test_seis_vistas_de_90_graus():
    panorama= _panorama(0.0, 0.0)
    vistas= list(views(panorama))
    assert len(vistas)== 6
    assert [yaw for yaw, _ in vistas]== [0.0, 60.0, 120.0, 180.0, 240.0, 300.0]
    assert all(vista.shape== (LADO_VISTA, LADO_VISTA, 3) for _, vista in vistas)


@pytest.mark.parametrize("lon", [0.0, 30.0, 89.0, 179.5, -179.7])
def test_rumo_volta_ao_panorama(lon):
    deteccoes= detect_panorama(DetetorDeMarcador(), "mapillary:1", _panorama(lon, 0.0))
    assert len(deteccoes)== 1
    x1, _, x2, _= deteccoes[0].bbox_xyxy
    rumo= object_bearing(0.0, (x1 + x2) / 2, LARGURA, 360.0)
    assert abs((rumo - lon + 180) % 360 - 180) < 1.0


def test_latitude_volta_ao_panorama():
    deteccoes= detect_panorama(DetetorDeMarcador(), "mapillary:1", _panorama(20.0, 25.0))
    assert len(deteccoes)== 1
    _, y1, _, y2= deteccoes[0].bbox_xyxy
    latitude= (0.5 - (y1 + y2) / 2 / ALTURA) * 180
    assert abs(latitude - 25.0) < 1.0


def test_sobreposicao_nao_duplica_deteccoes():
    panorama= _panorama(30.0, 0.0)
    com_marcador= [yaw for yaw, vista in views(panorama) if _caixa_do_marcador(vista) is not None]
    assert len(com_marcador)== 2
    detetor= DetetorDeMarcador()
    deteccoes= detect_panorama(detetor, "mapillary:1", panorama)
    assert detetor.chamadas== 6
    assert len(deteccoes)== 1


def test_nms_junta_caixas_na_costura():
    largura= 960
    a= Detection("i", "sinal", "stop", (950.0, 10.0, 990.0, 50.0), 0.9, False)
    b= Detection("i", "sinal", "stop", (0.0, 10.0, 25.0, 50.0), 0.8, False)
    mantidas= nms([a, b], largura)
    assert len(mantidas)== 1
    assert mantidas[0].confidence== 0.9


def test_nms_nao_junta_classes_diferentes():
    a= Detection("i", "sinal", "stop", (100.0, 10.0, 140.0, 50.0), 0.9, False)
    b= Detection("i", "sinal", "proibicao", (100.0, 10.0, 140.0, 50.0), 0.8, False)
    assert len(nms([a, b], 960))== 2


@pytest.mark.parametrize(("camera_type", "esperado"), [("spherical", 6), ("perspective", 1)])
def test_processar_usa_seis_vistas_no_panorama(tmp_path, camera_type, esperado):
    class DetetorContador:
        def __init__(self):
            self.chamadas= 0

        def detect(self, image_id: str, image: np.ndarray) -> list[Detection]:
            self.chamadas += 1
            return []

    registo= ImageRecord(
        "mapillary", camera_type, "a", "l", "u", None, 0, 0, 0, camera_type, "x"
    )
    save_anon(np.zeros((ALTURA, LARGURA, 3), np.uint8), tmp_path, registo)
    detetor= DetetorContador()
    processar([registo], lambda imagem: imagem, detetor, tmp_path, tmp_path / "checkpoint.jsonl")
    assert detetor.chamadas== esperado
