import csv
import io
import json
from pathlib import Path

import cv2
import numpy as np
import pytest
import yaml

from training.datasets import mtsd, openimages, vistas
from training.datasets.yolo import (
    escrever_data_yaml,
    escrever_data_yaml_conjunto,
    guardar_exemplo,
    ler_adiante,
    linhas_yolo,
    reduzir,
)
from training.train import ler_config

CONFIG= Path(__file__).parents[1] / "config"


class _Anonimizador:
    def __init__(self):
        self.chamadas= 0

    def __call__(self, imagem):
        self.chamadas+= 1
        return np.zeros_like(imagem)


def test_linhas_yolo_normaliza_corta_e_ignora_caixas_minusculas():
    linhas= linhas_yolo([(0, 0.1, 0.2, 0.3, 0.6), (1, -0.1, 0.0, 0.2, 1.2), (2, 0.5, 0.5, 0.5005, 0.6)])
    assert linhas == ["0 0.200000 0.400000 0.200000 0.400000", "1 0.100000 0.500000 0.200000 1.000000"]


def test_reduzir_mantem_proporcao_e_nao_aumenta():
    assert reduzir(np.zeros((1000, 4000, 3), np.uint8), 2000).shape == (500, 2000, 3)
    assert reduzir(np.zeros((100, 200, 3), np.uint8), 2000).shape == (100, 200, 3)


def test_guardar_exemplo_anonimiza_antes_de_gravar(tmp_path):
    anonimizador= _Anonimizador()
    imagem= np.full((400, 800, 3), 255, np.uint8)
    guardar_exemplo(tmp_path, "train", "a", imagem, [(0, 0.1, 0.1, 0.2, 0.2)], anonimizador, 400)
    gravada= cv2.imread(str(tmp_path / "images" / "train" / "a.jpg"))
    assert anonimizador.chamadas == 1
    assert gravada.shape == (200, 400, 3)
    assert gravada.max() < 10
    assert (tmp_path / "labels" / "train" / "a.txt").read_text().startswith("0 0.150000")


def test_data_yaml(tmp_path):
    conteudo= yaml.safe_load(escrever_data_yaml(tmp_path, ["outro", "candeeiro"]).read_text())
    assert conteudo["names"] == {0: "outro", 1: "candeeiro"}
    assert conteudo["train"] == "images/train"


def test_nomes_dos_datasets_existem_na_taxonomia():
    from pipeline.config import load_classes

    classes= load_classes(CONFIG / "classes.yaml")
    for nome in [*openimages.NOMES, *mtsd.NOMES]:
        assert classes.categoria_de(nome) is not None, nome


def _anotacao(objetos, largura=1000, altura=500):
    return {"width": largura, "height": altura, "ispano": False, "objects": objetos}


def _objeto(rotulo, xmin, ymin, xmax, ymax, **extra):
    return {"key": "k", "label": rotulo, "bbox": {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax, **extra}, "properties": {}}


def test_mtsd_caixas_mapeia_classes_e_ignora_dummy_e_complementares():
    falso= _objeto("other-sign", 0, 0, 10, 10)
    falso["properties"]["dummy"]= True
    caixas= mtsd.caixas_de(
        _anotacao(
            [
                _objeto("regulatory--stop--g1", 100, 50, 200, 150),
                _objeto("complementary--distance--g1", 0, 0, 10, 10),
                _objeto("warning--road-bump--g1", 500, 100, 600, 200),
                falso,
            ]
        )
    )
    assert caixas == [
        (mtsd.NOMES.index("stop"), 0.1, 0.1, 0.2, 0.3),
        (mtsd.NOMES.index("perigo"), 0.5, 0.2, 0.6, 0.4),
    ]


def test_mtsd_caixa_que_atravessa_a_costura_do_panorama():
    partes= {"left": {"xmin": 990, "ymin": 0, "xmax": 1000, "ymax": 50}, "right": {"xmin": 0, "ymin": 0, "xmax": 20, "ymax": 50}}
    caixas= mtsd.caixas_de(_anotacao([_objeto("information--parking--g1", 990, 0, 20, 50, cross_boundary=partes)]))
    assert [c[1] for c in caixas] == [0.99, 0.0]


def test_mtsd_converter_pasta_falsa(tmp_path):
    origem= tmp_path / "mtsd"
    for pasta in ("annotations", "images", "splits"):
        (origem / pasta).mkdir(parents=True)
    for divisao, chave in (("train", "t1"), ("val", "v1")):
        (origem / "splits" / f"{divisao}.txt").write_text(f"{chave}\nem_falta\n")
        cv2.imwrite(str(origem / "images" / f"{chave}.jpg"), np.full((500, 1000, 3), 200, np.uint8))
        (origem / "annotations" / f"{chave}.json").write_text(
            json.dumps(_anotacao([_objeto("regulatory--yield--g1", 100, 100, 200, 200)]))
        )
    saida= tmp_path / "yolo"
    feitas= mtsd.converter(origem, saida, _Anonimizador(), 2048)
    assert feitas == {"train": 1, "val": 1}
    assert (saida / "labels" / "val" / "v1.txt").read_text().startswith(f"{mtsd.NOMES.index('cedencia')} ")
    assert yaml.safe_load((saida / "data.yaml").read_text())["names"][0] == "stop"
    assert mtsd.converter(origem, saida, _Anonimizador(), 2048) == {"train": 1, "val": 1}


def test_mtsd_sem_splits(tmp_path):
    with pytest.raises(FileNotFoundError, match="splits"):
        mtsd.converter(tmp_path, tmp_path / "s", _Anonimizador(), 2048)


CABECALHO_CAIXAS= "ImageID,Source,LabelName,Confidence,XMin,XMax,YMin,YMax,IsOccluded,IsTruncated,IsGroupOf,IsDepiction,IsInside\n"


def test_openimages_ler_caixas_exclui_grupos_e_desenhos(tmp_path):
    ficheiro= tmp_path / "caixas.csv"
    ficheiro.write_text(
        CABECALHO_CAIXAS
        + "a,x,/m/033rq4,1,0.1,0.2,0.3,0.4,0,0,0,0,0\n"
        + "a,x,/m/01g317,1,0.1,0.2,0.3,0.4,0,0,0,0,0\n"
        + "b,x,/m/01mqdt,1,0.1,0.2,0.3,0.4,0,0,1,0,0\n"
        + "b,x,/m/01mqdt,1,0.5,0.6,0.3,0.4,0,0,0,0,0\n"
        + "c,x,/m/0bjyj5,1,0.1,0.2,0.3,0.4,0,0,0,1,0\n"
    )
    caixas= openimages.ler_caixas(ficheiro)
    assert caixas == {"a": [("candeeiro", 0.1, 0.3, 0.2, 0.4)]}


def test_openimages_escolher_respeita_o_maximo_por_classe():
    caixas= {f"i{n}": [("candeeiro", 0, 0, 1, 1)] for n in range(10)}
    caixas["raro"]= [("semaforo", 0, 0, 1, 1), ("candeeiro", 0, 0, 1, 1)]
    escolhidos= openimages.escolher(caixas, 3)
    assert "raro" in escolhidos
    assert len(escolhidos) <= 4


def test_openimages_info_tira_imagens_rodadas(tmp_path):
    ficheiro= tmp_path / "imagens.csv"
    ficheiro.write_text(
        "ImageID,Subset,OriginalURL,OriginalLandingURL,License,AuthorProfileURL,Author,Title,OriginalSize,OriginalMD5,Thumbnail300KURL,Rotation\n"
        "a,train,u,l,https://creativecommons.org/licenses/by/2.0/,p,Ana,t,1,m,th,0.0\n"
        "b,train,u,l,lic,p,Rui,t,1,m,th,90.0\n"
        "c,train,u,l,lic,p,Eva,t,1,m,th,\n"
    )
    info= openimages.ler_info(ficheiro, {"a", "b"})
    assert info == {"a": {"autor": "Ana", "licenca": "https://creativecommons.org/licenses/by/2.0/", "url": "l"}}


def test_config_de_treino_valida(tmp_path):
    dados= tmp_path / "data.yaml"
    dados.write_text("names: {}\n")
    config= tmp_path / "c.yaml"
    config.write_text(f"dados: {dados}\nmodelo: yolo11s.pt\nepocas: 1\nimgsz: 64\nlote: 1\nnome: t\ndestino: x.pt\n")
    assert ler_config(config)["epocas"] == 1
    config.write_text("dados: x\n")
    with pytest.raises(ValueError, match="faltam"):
        ler_config(config)


def test_configs_do_repositorio_estao_completas():
    for caminho in (Path(__file__).parents[1] / "training" / "configs").glob("*.yaml"):
        conteudo= yaml.safe_load(caminho.read_text())
        assert {"dados", "modelo", "epocas", "imgsz", "lote", "nome", "destino"} <= set(conteudo), caminho


def _quadrado(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _obj(rotulo, caixa):
    return {"id": 0, "label": rotulo, "polygon": _quadrado(*caixa)}


def test_vistas_junta_a_luminaria_ao_poste_e_mapeia_classes():
    anotacao= {
        "width": 1000,
        "height": 500,
        "objects": [
            _obj("object--street-light", (490, 50, 530, 80)),
            _obj("object--support--pole", (495, 60, 505, 450)),
            _obj("object--support--pole", (800, 60, 810, 450)),
            _obj("object--traffic-sign--front", (100, 100, 150, 150)),
            _obj("object--traffic-sign--back", (200, 100, 250, 150)),
            _obj("object--traffic-light--pedestrians", (300, 100, 320, 160)),
            _obj("object--trash-can", (400, 400, 440, 450)),
            _obj("nature--sky", (0, 0, 1000, 100)),
        ],
    }
    caixas= {c[0]: c[1:] for c in vistas.caixas_de(anotacao)}
    assert caixas[vistas.NOMES.index("candeeiro")] == (0.49, 0.1, 0.53, 0.9)
    assert caixas[vistas.NOMES.index("outro")] == (0.1, 0.2, 0.15, 0.3)
    assert vistas.NOMES.index("semaforo") in caixas
    assert vistas.NOMES.index("contentor") in caixas
    assert len(vistas.caixas_de(anotacao)) == 4


def test_vistas_luminaria_sem_poste_fica_so_com_a_cabeca():
    anotacao= {"width": 1000, "height": 500, "objects": [_obj("object--street-light", (490, 50, 530, 80))]}
    assert vistas.caixas_de(anotacao) == [(vistas.NOMES.index("candeeiro"), 0.49, 0.1, 0.53, 0.16)]


def test_vistas_ignora_caixas_minusculas_apos_reduzir():
    pequena= (0, 0.1, 0.1, 0.1 + 20 / 4000, 0.1 + 20 / 3000)
    grande= (0, 0.1, 0.1, 0.1 + 60 / 4000, 0.1 + 60 / 3000)
    assert not vistas.tamanho_suficiente(pequena, 4000, 3000, 1280)
    assert vistas.tamanho_suficiente(grande, 4000, 3000, 1280)


def test_vistas_escolher_e_regular():
    assert vistas.escolher(["d", "a", "c", "b"], 2) == ["a", "c"]
    assert vistas.escolher(["b", "a"], None) == ["a", "b"]


def test_vistas_converter_pasta_falsa_anonimiza_a_resolucao_maior(tmp_path):
    origem= tmp_path / "v"
    for divisao in ("training", "validation"):
        (origem / divisao / "images").mkdir(parents=True)
        (origem / divisao / "v2.0" / "polygons").mkdir(parents=True)
        chave= f"k_{divisao}"
        cv2.imwrite(str(origem / divisao / "images" / f"{chave}.jpg"), np.full((3000, 4000, 3), 200, np.uint8))
        poligonos= {"width": 4000, "height": 3000, "objects": [_obj("object--traffic-sign--front", (1000, 1000, 1400, 1400))]}
        (origem / divisao / "v2.0" / "polygons" / f"{chave}.json").write_text(json.dumps(poligonos))
    tamanhos= []

    class Anonimizador:
        def __call__(self, imagem):
            tamanhos.append(imagem.shape[:2])
            return np.zeros_like(imagem)

    registo= io.StringIO()
    saida= tmp_path / "yolo"
    feitas= vistas.converter(origem, saida, Anonimizador(), 1280, {"train": 5, "val": 5}, csv.writer(registo), 1)
    assert feitas == {"train": 1, "val": 1}
    assert tamanhos == [(1536, 2048), (1536, 2048)]
    assert cv2.imread(str(saida / "images" / "train" / "k_training.jpg")).shape[:2] == (960, 1280)
    assert registo.getvalue().count("CC BY-NC-SA 4.0") == 2
    assert (saida / "labels" / "val" / "k_validation.txt").read_text().startswith(f"{vistas.NOMES.index('outro')} ")


def test_vistas_sem_poligonos(tmp_path):
    with pytest.raises(FileNotFoundError, match="Vistas"):
        vistas.converter(tmp_path, tmp_path / "s", _Anonimizador(), 1280, {}, None)


def test_ler_adiante_nunca_passa_da_janela_e_mantem_a_ordem():
    lidos= []
    consumidos= []

    def ler(item):
        lidos.append(item)
        return item * 2

    maximo_a_frente= 0
    for item, resultado in ler_adiante(ler, range(50), 4, janela=5):
        consumidos.append(item)
        maximo_a_frente= max(maximo_a_frente, len(lidos) - len(consumidos))
        assert resultado == item * 2
    assert consumidos == list(range(50))
    assert maximo_a_frente <= 5


def test_ler_adiante_aceita_vazio_e_menos_itens_que_a_janela():
    assert list(ler_adiante(lambda i: i, [], 2)) == []
    assert list(ler_adiante(lambda i: i, [1, 2], 2, janela=8)) == [(1, 1), (2, 2)]


def test_data_yaml_conjunto(tmp_path):
    pastas= [tmp_path / "a", tmp_path / "b"]
    conteudo= yaml.safe_load(escrever_data_yaml_conjunto(tmp_path / "g.yaml", pastas, ["x"]).read_text())
    assert conteudo["train"] == [str((p / "images" / "train").resolve()) for p in pastas]
    assert conteudo["names"] == {0: "x"}
