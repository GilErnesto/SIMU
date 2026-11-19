import pytest

from pipeline.config import ErroPipeline, Municipio, aplicar_bbox

BASE= Municipio("Aveiro", (-8.6625, 40.6291, -8.6581, 40.6382), "EPSG:3763")


def test_sem_texto_devolve_o_mesmo_municipio():
    assert aplicar_bbox(BASE, None) is BASE
    assert aplicar_bbox(BASE, "") is BASE


def test_texto_substitui_so_a_bbox():
    novo= aplicar_bbox(BASE, "-8.66,40.62,-8.65,40.63")
    assert novo.bbox == (-8.66, 40.62, -8.65, 40.63)
    assert novo.nome == BASE.nome
    assert novo.crs_metrico == BASE.crs_metrico


def test_espacos_a_volta_dos_valores_sao_aceites():
    assert aplicar_bbox(BASE, " -8.66, 40.62, -8.65, 40.63 ").bbox == (-8.66, 40.62, -8.65, 40.63)


@pytest.mark.parametrize("texto", ["1,2,3", "a,b,c,d", "-8.66,40.62,-8.65,40.63,1"])
def test_formato_invalido(texto):
    with pytest.raises(ErroPipeline):
        aplicar_bbox(BASE, texto)


def test_minimos_tem_de_ser_menores_que_os_maximos():
    with pytest.raises(ErroPipeline):
        aplicar_bbox(BASE, "-8.65,40.62,-8.66,40.63")


def test_valores_fora_de_limites_sao_recusados():
    with pytest.raises(ErroPipeline):
        aplicar_bbox(BASE, "-8.66,40.62,-8.65,200")
