from pathlib import Path

import pytest
from pyproj import Transformer

from pipeline.config import load_classes, load_municipio
from pipeline.errors import ErroPipeline
from pipeline.referencia import juntar, obter_features, para_geojson, para_pontos
from pipeline.rotulos_mapillary import classificar

CONFIG= Path(__file__).parents[1] / "config"
MUNICIPIO= load_municipio(CONFIG / "municipio.yaml")
PARA_GRAUS= Transformer.from_crs(MUNICIPIO.crs_metrico, "EPSG:4326", always_xy=True)
PARA_METROS= Transformer.from_crs("EPSG:4326", MUNICIPIO.crs_metrico, always_xy=True)
X0, Y0= PARA_METROS.transform(-8.66, 40.633)


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("regulatory--stop--g1", ("sinal", "stop")),
        ("regulatory--yield--g1", ("sinal", "cedencia")),
        ("regulatory--maximum-speed-limit-40--g1", ("sinal", "limite_velocidade")),
        ("regulatory--no-parking--g1", ("sinal", "proibicao")),
        ("regulatory--weight-limit--g1", ("sinal", "proibicao")),
        ("regulatory--turn-left--g1", ("sinal", "obrigacao")),
        ("regulatory--bicycles-only--g1", ("sinal", "obrigacao")),
        ("regulatory--roundabout--g1", ("sinal", "obrigacao")),
        ("regulatory--one-way-right--g1", ("sinal", "informacao")),
        ("regulatory--priority-road--g4", ("sinal", "outro")),
        ("warning--road-bump--g1", ("sinal", "perigo")),
        ("information--pedestrians-crossing--g1", ("sinal", "informacao")),
        ("object--traffic-sign--front", ("sinal", "outro")),
        ("other-sign", ("sinal", "outro")),
        ("object--traffic-light--pedestrians-back", ("sinal", "semaforo")),
        ("object--street-light", ("iluminacao", "luz")),
        ("object--trash-can", ("residuos", "papeleira")),
        ("object--traffic-sign--back", None),
        ("complementary--chevron-left--g1", None),
        ("object--manhole", None),
        ("marking--discrete--stop-line", None),
    ],
)
def test_classificar(valor, esperado):
    assert classificar(valor) == esperado


def test_costas_so_quando_pedido():
    assert classificar("object--traffic-sign--back", incluir_costas=True) == ("sinal", "outro")


def test_classes_do_mapeamento_existem_na_taxonomia():
    classes= load_classes(CONFIG / "classes.yaml")
    for valor in ("regulatory--stop--g1", "object--street-light", "object--trash-can", "object--traffic-light--x"):
        categoria, classe= classificar(valor)
        assert classes.categoria_de(classe).nome == categoria


def _ponto(dx, dy, categoria, classe):
    lon, lat= PARA_GRAUS.transform(X0 + dx, Y0 + dy)
    return {"categoria": categoria, "classe": classe, "lon": lon, "lat": lat, "valor_original": "", "id_mapillary": ""}


def test_juntar_absorve_genericos_e_mantem_sinais_diferentes_no_poste():
    pontos= [
        _ponto(0, 0, "sinal", "outro"),
        _ponto(1, 0, "sinal", "stop"),
        _ponto(1.5, 0, "sinal", "proibicao"),
        _ponto(1, 0.5, "sinal", "stop"),
        _ponto(1, 0, "iluminacao", "candeeiro"),
        _ponto(20, 0, "sinal", "outro"),
    ]
    ficam= juntar(pontos, MUNICIPIO.crs_metrico)
    assert sorted((p["categoria"], p["classe"]) for p in ficam) == [
        ("iluminacao", "candeeiro"),
        ("sinal", "outro"),
        ("sinal", "proibicao"),
        ("sinal", "stop"),
    ]


class _Resposta:
    def __init__(self, dados, estado=200):
        self.status_code= estado
        self._dados= dados

    def json(self):
        return {"data": self._dados}


class _Sessao:
    def __init__(self, respostas):
        self.headers= {}
        self.respostas= list(respostas)
        self.pedidos= []

    def get(self, url, params, timeout):
        self.pedidos.append(params)
        return self.respostas.pop(0) if self.respostas else _Resposta([])


def _item(id_, lon, lat, valor="object--street-light"):
    return {"id": id_, "object_value": valor, "geometry": {"type": "Point", "coordinates": [lon, lat]}}


def test_obter_features_junta_tiles_e_corta_a_bbox():
    bbox= (-8.67, 40.63, -8.66, 40.64)
    dentro= _item("1", -8.665, 40.635)
    fora= _item("2", -8.60, 40.635)
    sessao= _Sessao([_Resposta([dentro, fora]), _Resposta([dentro])])
    vistas= obter_features(bbox, "token", sessao)
    assert [v["id"] for v in vistas] == ["1"]
    assert sessao.headers["Authorization"] == "OAuth token"
    assert len(sessao.pedidos) == 4


def test_obter_features_falha_com_erro_http():
    with pytest.raises(ErroPipeline, match="403"):
        obter_features((-8.67, 40.63, -8.66, 40.64), "t", _Sessao([_Resposta([], 403)]))


def test_para_pontos_e_geojson():
    pontos= para_pontos([_item("1", -8.66, 40.63), _item("2", -8.66, 40.63, "object--manhole")])
    colecao= para_geojson(pontos)
    assert len(colecao["features"]) == 1
    propriedades= colecao["features"][0]["properties"]
    assert propriedades["categoria"] == "iluminacao"
    assert propriedades["classe"] == "luz"
    assert propriedades["origem"] == "mapillary_map_features"
