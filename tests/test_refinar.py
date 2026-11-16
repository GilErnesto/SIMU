from pathlib import Path

import numpy as np
import pytest

from pipeline.config import load_classes
from pipeline.models import Detection

torch= pytest.importorskip("torch")

from pipeline.detect.refinar import DuasFases, Refinador, recortar

CLASSES= load_classes(Path(__file__).parents[1] / "config" / "classes.yaml")


class Entradas(dict):
    def to(self, _):
        return self


class ProcessadorFalso:
    def __init__(self):
        self.chamadas= []

    def __call__(self, text, images, return_tensors, padding):
        self.chamadas.append((list(text), len(images)))
        return Entradas()


class ModeloFalso:
    def __init__(self, logits):
        self.logits= logits

    def __call__(self, **_):
        class Saida:
            pass

        saida= Saida()
        saida.logits_per_image= torch.tensor(self.logits, dtype=torch.float32)
        return saida


def _refinador(logits, limiar= 0.5):
    return Refinador(ProcessadorFalso(), ModeloFalso(logits), CLASSES, limiar)


def _lista(categoria):
    config= CLASSES.categorias[categoria]
    itens= []
    for classe, descricao in config.descricoes.items():
        itens.extend([classe] * (1 if isinstance(descricao, str) else len(descricao)))
    itens.extend([None] * len(config.negativos))
    return itens


def _indice(categoria, classe):
    return _lista(categoria).index(classe)


def _total(categoria):
    return len(_lista(categoria))


def _logits_para(categoria, classe, forca= 10.0):
    linha= [0.0] * _total(categoria)
    linha[_indice(categoria, classe)]= forca
    return linha


def _imagem():
    return np.full((200, 300, 3), 120, dtype=np.uint8)


class DetetorFalso:
    def __init__(self, detecoes):
        self.detecoes= detecoes

    def detect(self, image_id, image):
        return list(self.detecoes)


def _det(categoria, classe, caixa= (100.0, 50.0, 160.0, 120.0), confianca= 0.64):
    return Detection("img", categoria, classe, caixa, confianca, False)


def test_classificar_devolve_a_melhor_descricao():
    refinador= _refinador([_logits_para("sinal", "stop")])
    previsto= refinador.classificar("sinal", [_imagem()])
    assert previsto[0][0] == "stop"
    assert previsto[0][1] > 0.99
    textos= refinador.processor.chamadas[0][0]
    assert textos[0].startswith("a photo of ")
    assert len(textos) == _total("sinal")


def test_geral_passa_a_especifico_com_confianca_combinada():
    refinador= _refinador([_logits_para("sinal", "stop")])
    fases= DuasFases(DetetorFalso([_det("sinal", "outro")]), refinador, CLASSES)
    resultado= fases.detect("img", _imagem())
    assert resultado[0].class_name == "stop"
    assert resultado[0].confidence == pytest.approx((0.64 * 1.0) ** 0.5, abs=0.01)
    assert resultado[0].bbox_xyxy == (100.0, 50.0, 160.0, 120.0)


def test_probabilidade_baixa_mantem_o_geral():
    refinador= _refinador([[0.0] * _total("sinal")], limiar= 0.5)
    fases= DuasFases(DetetorFalso([_det("sinal", "outro")]), refinador, CLASSES)
    resultado= fases.detect("img", _imagem())
    assert resultado[0].class_name == "outro"
    assert resultado[0].confidence == 0.64


def test_so_refina_categorias_com_descricoes():
    refinador= _refinador([_logits_para("sinal", "stop"), _logits_para("sinal", "stop")])
    detecoes= [_det("sinal", "semaforo"), _det("iluminacao", "candeeiro"), _det("sinal", "outro")]
    resultado= DuasFases(DetetorFalso(detecoes), refinador, CLASSES).detect("img", _imagem())
    assert [d.class_name for d in resultado] == ["stop", "candeeiro", "stop"]
    assert refinador.processor.chamadas[0][1] == 2


def test_semaforo_do_passo_1_tambem_pode_ser_descartado():
    refinador= _refinador([_logits_negativo("sinal")])
    resultado= DuasFases(DetetorFalso([_det("sinal", "semaforo")]), refinador, CLASSES).detect("img", _imagem())
    assert resultado == []


def test_papeleira_do_passo_1_passa_a_contentor_de_rodas():
    refinador= _refinador([_logits_para("residuos", "indiferenciado")])
    resultado= DuasFases(DetetorFalso([_det("residuos", "papeleira")]), refinador, CLASSES).detect("img", _imagem())
    assert [d.class_name for d in resultado] == ["indiferenciado"]


def test_lixo_geral_passa_a_tipo_de_contentor():
    refinador= _refinador([_logits_para("residuos", "subterraneo")])
    fases= DuasFases(DetetorFalso([_det("residuos", "contentor")]), refinador, CLASSES)
    assert fases.detect("img", _imagem())[0].class_name == "subterraneo"


def test_recorte_demasiado_pequeno_e_ignorado():
    refinador= _refinador([_logits_para("sinal", "stop")])
    pequena= _det("sinal", "outro", caixa= (10.0, 10.0, 14.0, 14.0))
    resultado= DuasFases(DetetorFalso([pequena]), refinador, CLASSES).detect("img", _imagem())
    assert resultado[0].class_name == "outro"
    assert refinador.processor.chamadas == []


def test_recortar_respeita_os_limites():
    recorte= recortar(_imagem(), (0.0, 0.0, 300.0, 200.0))
    assert recorte.shape[:2] == (200, 300)
    assert recortar(_imagem(), (290.0, 190.0, 292.0, 192.0)) is None


def _logits_negativo(categoria, forca= 10.0):
    total= _total(categoria)
    linha= [0.0] * total
    linha[total - 1]= forca
    return linha


def test_resposta_negativa_descarta_a_deteccao():
    refinador= _refinador([_logits_negativo("sinal")])
    fases= DuasFases(DetetorFalso([_det("sinal", "outro")]), refinador, CLASSES)
    assert fases.detect("img", _imagem()) == []


def test_negativo_com_pouca_probabilidade_mantem_a_deteccao():
    refinador= _refinador([[0.0] * _total("residuos")])
    fases= DuasFases(DetetorFalso([_det("residuos", "contentor")]), refinador, CLASSES)
    resultado= fases.detect("img", _imagem())
    assert [d.class_name for d in resultado] == ["contentor"]


def test_negativos_nao_afetam_categorias_sem_descricoes():
    refinador= _refinador([_logits_negativo("sinal")])
    fases= DuasFases(DetetorFalso([_det("iluminacao", "candeeiro")]), refinador, CLASSES)
    assert [d.class_name for d in fases.detect("img", _imagem())] == ["candeeiro"]


def test_varios_textos_do_mesmo_tipo_somam_a_probabilidade():
    ids= _lista("sinal")
    posicoes= [i for i, classe in enumerate(ids) if classe == "informacao"]
    assert len(posicoes) >= 2
    linha= [0.0] * len(ids)
    for i in posicoes:
        linha[i]= 2.0
    linha[ids.index("stop")]= 2.5
    previsto= _refinador([linha]).classificar("sinal", [_imagem()])
    assert previsto[0][0] == "informacao"
    assert previsto[0][1] > 0.4
