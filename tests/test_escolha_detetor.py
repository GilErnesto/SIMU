from argparse import Namespace

import pytest

from pipeline.run import tipo_de_detetor


def test_auto_usa_o_yolo_quando_ha_pesos(tmp_path):
    pesos= tmp_path / "d.pt"
    pesos.write_bytes(b"x")
    assert tipo_de_detetor(Namespace(detetor="auto", pesos=str(pesos))) == "yolo"


def test_auto_cai_para_o_owlv2_sem_pesos(tmp_path):
    assert tipo_de_detetor(Namespace(detetor="auto", pesos=str(tmp_path / "nao_existe.pt"))) == "owlv2"


@pytest.mark.parametrize("escolha", ["owlv2", "yolo"])
def test_escolha_explicita_nao_depende_dos_pesos(tmp_path, escolha):
    assert tipo_de_detetor(Namespace(detetor=escolha, pesos=str(tmp_path / "nao_existe.pt"))) == escolha
