from pathlib import Path

import pytest

from pipeline.config import load_classes, load_municipio
from pipeline.errors import ErroPipeline

CONFIG= Path(__file__).parents[1] / "config"


def test_municipio_real():
    municipio= load_municipio(CONFIG / "municipio.yaml")
    lon_min, lat_min, lon_max, lat_max= municipio.bbox
    assert lon_min < lon_max and lat_min < lat_max
    assert municipio.crs_metrico.startswith("EPSG:")


def test_classes_reais():
    classes= load_classes(CONFIG / "classes.yaml")
    assert set(classes.categorias) == {"sinal", "iluminacao", "residuos"}
    assert classes.categoria_de("stop").nome == "sinal"
    assert classes.categoria_de("candeeiro").nome == "iluminacao"
    assert classes.categoria_de("inexistente") is None
    assert classes.categorias["residuos"].raio_dedup_m == 10


def test_bbox_invertida(tmp_path):
    ficheiro= tmp_path / "municipio.yaml"
    ficheiro.write_text(
        "nome: X\nbbox: {lon_min: 1, lat_min: 0, lon_max: 0, lat_max: 1}\ncrs_metrico: EPSG:3763\n"
    )
    with pytest.raises(ErroPipeline, match="bbox inválida"):
        load_municipio(ficheiro)


def test_ficheiro_em_falta(tmp_path):
    with pytest.raises(ErroPipeline, match="não encontrado"):
        load_municipio(tmp_path / "nao_existe.yaml")
