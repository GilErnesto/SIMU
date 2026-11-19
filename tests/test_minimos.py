import math

import pytest

from pipeline.geolocate.minimos import ponto_minimos_quadrados
from pipeline.geolocate.triangulate import intersect


def _rumo(origem, alvo):
    return math.degrees(math.atan2(alvo[0] - origem[0], alvo[1] - origem[1])) % 360


def test_raios_exatos_dao_o_alvo():
    alvo= (10.0, 30.0)
    origens= [(0.0, 0.0), (8.0, 0.0), (30.0, 0.0)]
    rumos= [_rumo(o, alvo) for o in origens]
    x, y= ponto_minimos_quadrados(origens, rumos)
    assert (x, y) == pytest.approx(alvo, abs=1e-6)


def test_raios_paralelos_nao_dao_ponto():
    assert ponto_minimos_quadrados([(0.0, 0.0), (5.0, 0.0)], [0.0, 0.0]) is None


def test_ponto_atras_da_camara_nao_e_aceite():
    assert ponto_minimos_quadrados([(0.0, 0.0), (10.0, 0.0)], [0.0, 45.0]) is None


def test_erro_menor_que_a_media_das_intersecoes_com_ruido_no_par_curto():
    alvo= (10.0, 30.0)
    origens= [(0.0, 0.0), (8.0, 0.0), (30.0, 0.0)]
    rumos= [_rumo(o, alvo) for o in origens]
    rumos[0]+= 1.0
    pares= [
        intersect(origens[i], rumos[i], origens[j], rumos[j]) for i, j in ((0, 1), (0, 2), (1, 2))
    ]
    media= (sum(p[0] for p in pares) / 3, sum(p[1] for p in pares) / 3)
    ls= ponto_minimos_quadrados(origens, rumos)
    assert math.dist(ls, alvo) < math.dist(media, alvo)
