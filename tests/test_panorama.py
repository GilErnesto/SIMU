from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from pipeline.anonymize.egoblur import save_anon
from pipeline.config import load_classes
from pipeline.detect.panorama import (
    LADO_VISTA,
    deteccoes_inclinadas,
    detect_panorama,
    juntar_inclinadas,
    nms,
    views,
    views_inclinadas,
)
from pipeline.geolocate.bearing import object_bearing
from pipeline.models import Detection, ImageRecord
from pipeline.run import inclinadas_de, processar

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


def test_o_centro_da_vista_inclinada_e_a_longitude_e_a_latitude_pedidas():
    panorama= _panorama(0.0, 35.0)
    yaw, vista= next(iter(views_inclinadas(panorama, 35.0)))
    caixa= _caixa_do_marcador(vista)
    assert yaw== 0.0
    assert vista.shape== (LADO_VISTA, LADO_VISTA, 3)
    assert abs((caixa[0] + caixa[2]) / 2 - LADO_VISTA / 2) < 12
    assert abs((caixa[1] + caixa[3]) / 2 - LADO_VISTA / 2) < 12


def test_marcador_a_60_graus_so_se_ve_nas_vistas_inclinadas():
    panorama= _panorama(20.0, 60.0)
    assert detect_panorama(DetetorDeMarcador(), "mapillary:1", panorama)== []
    brutas= deteccoes_inclinadas(DetetorDeMarcador(), "mapillary:1", panorama, {35.0: frozenset({"sinal"})})
    assert len(brutas) >= 1
    erros= []
    for deteccao in brutas:
        x1, y1, x2, y2= deteccao.bbox_xyxy
        rumo= object_bearing(0.0, (x1 + x2) / 2, LARGURA, 360.0)
        erros.append(max(abs((rumo - 20.0 + 180) % 360 - 180), abs((0.5 - (y1 + y2) / 2 / ALTURA) * 180 - 60.0)))
    assert min(erros) < 4.0


def test_vistas_inclinadas_acrescentam_seis_chamadas_e_ignoram_categorias_nao_pedidas():
    detetor= DetetorDeMarcador()
    panorama= _panorama(20.0, 60.0)
    detect_panorama(detetor, "mapillary:1", panorama, inclinadas={35.0: frozenset({"sinal"})})
    assert detetor.chamadas== 12
    assert deteccoes_inclinadas(DetetorDeMarcador(), "mapillary:1", panorama, {35.0: frozenset({"iluminacao"})})== []


def _luz(caixa, confianca= 0.8, categoria= "iluminacao"):
    return Detection("i", categoria, "luz", caixa, confianca, False)


def test_juntar_inclinadas_acrescenta_so_caixas_grandes_e_sem_sobreposicao():
    base= [_luz((100.0, 100.0, 140.0, 400.0))]
    grande_livre= _luz((300.0, 50.0, 360.0, 400.0))
    pequena= _luz((500.0, 100.0, 520.0, 160.0))
    sobreposta= _luz((105.0, 50.0, 150.0, 300.0))
    dentro= _luz((110.0, 150.0, 130.0, 350.0))
    outra_categoria= _luz((100.0, 100.0, 140.0, 400.0), categoria= "sinal")
    resultado= juntar_inclinadas(base, [grande_livre, pequena, sobreposta, dentro, outra_categoria], 960, 480)
    assert resultado== base + [grande_livre, outra_categoria]


def test_juntar_inclinadas_exige_confianca_minima():
    base= []
    fraca= _luz((300.0, 50.0, 360.0, 400.0), confianca= 0.4)
    forte= _luz((600.0, 50.0, 660.0, 400.0), confianca= 0.6)
    assert juntar_inclinadas(base, [fraca, forte], 960, 480)== [forte]


def test_juntar_inclinadas_sem_inclinadas_devolve_a_base():
    base= [_luz((100.0, 100.0, 140.0, 400.0))]
    assert juntar_inclinadas(base, [], 960, 480)== base


def test_a_iluminacao_pede_vistas_inclinadas_e_um_detetor_sem_classes_nao():
    classes= load_classes(Path(__file__).parents[1] / "config" / "classes.yaml")
    assert inclinadas_de(SimpleNamespace(classes=classes))== {35.0: frozenset({"iluminacao"})}
    assert inclinadas_de(DetetorDeMarcador())== {}


def test_nms_junta_caixas_na_costura():
    largura= 960
    a= Detection("i", "sinal", "stop", (950.0, 10.0, 990.0, 50.0), 0.9, False)
    b= Detection("i", "sinal", "stop", (0.0, 10.0, 25.0, 50.0), 0.8, False)
    mantidas= nms([a, b], largura)
    assert len(mantidas)== 1
    assert mantidas[0].confidence== 0.9


def test_nms_junta_classes_diferentes_da_mesma_categoria():
    a= Detection("i", "sinal", "stop", (100.0, 10.0, 140.0, 50.0), 0.9, False)
    b= Detection("i", "sinal", "proibicao", (100.0, 10.0, 140.0, 50.0), 0.8, False)
    mantidas= nms([a, b], 960)
    assert [d.class_name for d in mantidas] == ["stop"]


def test_nms_nao_junta_categorias_diferentes():
    a= Detection("i", "sinal", "stop", (100.0, 10.0, 140.0, 50.0), 0.9, False)
    b= Detection("i", "iluminacao", "candeeiro", (100.0, 10.0, 140.0, 50.0), 0.8, False)
    assert len(nms([a, b], 960)) == 2


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
