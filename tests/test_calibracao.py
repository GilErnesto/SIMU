from pathlib import Path

import pytest

from pipeline.config import calibrar_confianca, load_classes
from pipeline.errors import ErroPipeline

CONFIG= Path(__file__).parents[1] / "config"


def _categoria(tmp_path, calibracao):
    ficheiro= tmp_path / "classes.yaml"
    ficheiro.write_text(
        "categorias:\n"
        "  iluminacao:\n"
        "    classes: [luz]\n"
        "    raio_dedup_m: 6.5\n"
        "    altura_m: 6\n"
        f"    calibracao: {calibracao}\n",
        encoding="utf-8",
    )
    return load_classes(ficheiro).categorias["iluminacao"]


def test_ponto_calibrado_devolve_o_valor_do_par(tmp_path):
    categoria= _categoria(tmp_path, "[[0.3, 0.86], [0.5, 0.9]]")
    assert calibrar_confianca(categoria, 0.3) == pytest.approx(0.86)
    assert calibrar_confianca(categoria, 0.5) == pytest.approx(0.9)


def test_entre_dois_pares_interpola_linearmente(tmp_path):
    categoria= _categoria(tmp_path, "[[0.3, 0.86], [0.5, 0.9]]")
    assert calibrar_confianca(categoria, 0.4) == pytest.approx(0.88)


def test_fora_do_intervalo_prende_nos_extremos(tmp_path):
    categoria= _categoria(tmp_path, "[[0.3, 0.86], [0.5, 0.9]]")
    assert calibrar_confianca(categoria, 0.1) == pytest.approx(0.86)
    assert calibrar_confianca(categoria, 0.9) == pytest.approx(0.9)


def test_sem_calibracao_devolve_a_confianca_igual(tmp_path):
    categoria= _categoria(tmp_path, "[]")
    assert calibrar_confianca(categoria, 0.42) == 0.42


@pytest.mark.parametrize(
    "calibracao",
    ["[[0.5, 0.9], [0.3, 0.86]]", "[[0.3, 0.86], [0.3, 0.9]]", "[[0.3, 1.2]]", "[[-0.1, 0.5]]"],
)
def test_calibracao_invalida_falha(tmp_path, calibracao):
    with pytest.raises(ErroPipeline, match="classes.yaml inválido"):
        _categoria(tmp_path, calibracao)


def test_classes_reais_tem_calibracao_so_na_iluminacao():
    classes= load_classes(CONFIG / "classes.yaml")
    assert classes.categorias["iluminacao"].calibracao
    assert classes.categorias["sinal"].calibracao == ()
