import base64

import pytest

from pipeline.errors import ErroPipeline
from pipeline.ingest.vectortile import caixa_normalizada, descodificar

CEDENCIA= "GiV4AgoGbXB5LW9yKIAgEhYYAwgBIhAJjCCqGxoAkgP6AQAAkQMP"
VIRAR_ESQUERDA= "GiV4AgoGbXB5LW9yKIAgEhYYAwgBIhAJoCDgFxoAvAP2AQAAuwMP"


def test_caixa_de_uma_resposta_real_do_mapillary():
    x0, y0, x1, y1= caixa_normalizada(CEDENCIA)
    assert (x0, y0) == pytest.approx((0.50146, 0.42700), abs=1e-4)
    assert (x1, y1) == pytest.approx((0.53198, 0.47607), abs=1e-4)


def test_outra_resposta_real_fica_acima_da_primeira():
    _, y0_a, _, y1_a= caixa_normalizada(CEDENCIA)
    _, y0_b, _, y1_b= caixa_normalizada(VIRAR_ESQUERDA)
    assert y1_b < y1_a
    assert y0_b < y0_a


def test_descodificar_devolve_um_anel_fechado_com_extent():
    (aneis, extent), = descodificar(CEDENCIA)
    assert extent == 4096
    assert len(aneis) == 1
    assert len(aneis[0]) >= 3


def test_base64_invalido():
    with pytest.raises(ErroPipeline, match="base64"):
        descodificar("isto não é base64!")


def test_geometria_truncada():
    bruto= base64.b64decode(CEDENCIA)
    cortado= base64.b64encode(bruto[:-6]).decode()
    with pytest.raises(ErroPipeline, match="truncada"):
        descodificar(cortado)


def test_sem_camadas_nao_tem_caixa():
    assert caixa_normalizada(base64.b64encode(b"").decode()) is None
