from argparse import Namespace
from types import SimpleNamespace

import pytest

from pipeline.detect.conjunto import Conjunto
from pipeline.detect.infer import Detector, Limiares
from pipeline.detect.refinar import DuasFases, Refinador
from pipeline.run import _detetor, tipo_de_detetor


def _args(pesos: str, **extra):
    base= {"detetor": "yolo", "pesos": pesos, "limiar": 0.3, "sem_refinar": False, "limiar_classe": 0.0}
    return Namespace(**{**base, **extra})


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "tipo_residuos.npz").write_bytes(b"x")
    carregadas= {}
    monkeypatch.setattr(
        Detector, "from_weights", classmethod(lambda cls, pesos, classes, limiar, aumentar: SimpleNamespace(pesos=pesos))
    )
    monkeypatch.setattr(
        Refinador, "load", classmethod(lambda cls, classes, limiar, cabecas: carregadas.update(cabecas) or "refinador")
    )
    return tmp_path, carregadas


def test_detetor_refina_com_as_cabecas_que_existem(ambiente):
    tmp_path, carregadas= ambiente
    pesos= tmp_path / "a.pt"
    pesos.write_bytes(b"p")
    resultado= _detetor(_args(str(pesos)), "classes")
    assert isinstance(resultado, Limiares)
    assert isinstance(resultado.detetor, DuasFases)
    assert resultado.detetor.detetor.pesos == pesos
    assert set(carregadas) == {"residuos"}
    assert isinstance(resultado.versao, str)


def test_detetor_com_varios_pesos_refina_cada_membro(ambiente):
    tmp_path, _= ambiente
    pesos= [tmp_path / "a.pt", tmp_path / "b.pt"]
    for p in pesos:
        p.write_bytes(b"p")
    resultado= _detetor(_args(",".join(str(p) for p in pesos)), "classes", limiares=False)
    assert isinstance(resultado, Conjunto)
    assert all(isinstance(m, DuasFases) for m in resultado.detetores)


def test_detetor_sem_refinar_nao_carrega_cabecas(ambiente):
    tmp_path, carregadas= ambiente
    pesos= tmp_path / "a.pt"
    pesos.write_bytes(b"p")
    resultado= _detetor(_args(str(pesos), sem_refinar=True), "classes", limiares=False)
    assert resultado.pesos == pesos
    assert carregadas == {}


def test_auto_usa_o_yolo_quando_ha_pesos(tmp_path):
    pesos= tmp_path / "d.pt"
    pesos.write_bytes(b"x")
    assert tipo_de_detetor(Namespace(detetor="auto", pesos=str(pesos))) == "yolo"


def test_auto_cai_para_o_owlv2_sem_pesos(tmp_path):
    assert tipo_de_detetor(Namespace(detetor="auto", pesos=str(tmp_path / "nao_existe.pt"))) == "owlv2"


@pytest.mark.parametrize("escolha", ["owlv2", "yolo"])
def test_escolha_explicita_nao_depende_dos_pesos(tmp_path, escolha):
    assert tipo_de_detetor(Namespace(detetor=escolha, pesos=str(tmp_path / "nao_existe.pt"))) == escolha
