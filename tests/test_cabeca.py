from pathlib import Path

import numpy as np
import pytest

from pipeline.config import load_classes
from pipeline.detect.cabeca import Cabeca, treinar
from pipeline.errors import ErroPipeline, ModeloEmFalta

torch= pytest.importorskip("torch")

from pipeline.detect.refinar import Refinador

CLASSES= load_classes(Path(__file__).parents[1] / "config" / "classes.yaml")


def _dados(n= 60, semente= 0):
    gerador= np.random.default_rng(semente)
    centros= {"stop": [4, 0, 0], "cedencia": [0, 4, 0], "perigo": [0, 0, 4]}
    X= []
    y= []
    for classe, centro in centros.items():
        X.append(gerador.normal(centro, 0.5, size=(n, 3)))
        y.extend([classe] * n)
    return np.vstack(X), y


def test_treinar_separa_classes_bem_separadas():
    X, y= _dados()
    cabeca= treinar(X, y)
    previstas= [classe for classe, _ in cabeca.prever(X)]
    assert np.mean([a == b for a, b in zip(previstas, y, strict=True)]) > 0.98
    assert sorted(cabeca.classes) == ["cedencia", "perigo", "stop"]


def test_probabilidades_somam_um():
    X, y= _dados(10)
    soma= treinar(X, y).probabilidades(X).sum(axis=1)
    assert soma == pytest.approx(np.ones(len(X)), abs=1e-5)


def test_guardar_e_carregar_sem_pickle(tmp_path):
    X, y= _dados(10)
    cabeca= treinar(X, y)
    cabeca.guardar(tmp_path / "pasta" / "c.npz")
    outra= Cabeca.carregar(tmp_path / "pasta" / "c.npz")
    assert outra.classes == cabeca.classes
    assert outra.prever(X) == cabeca.prever(X)


def test_carregar_em_falta(tmp_path):
    with pytest.raises(ModeloEmFalta):
        Cabeca.carregar(tmp_path / "nao_existe.npz")


def test_treinar_com_uma_classe():
    with pytest.raises(ErroPipeline, match="duas classes"):
        treinar(np.zeros((4, 3)), ["a"] * 4)


def test_formas_incoerentes():
    with pytest.raises(ErroPipeline, match="incoerentes"):
        Cabeca(["a", "b"], np.zeros((3, 2)), np.zeros(2))


class _Entradas(dict):
    def to(self, _):
        return self


class _Processador:
    def __call__(self, text, images, return_tensors, padding):
        return _Entradas()


class _Modelo:
    def __init__(self, logits, embeddings):
        self.logits= logits
        self.embeddings= embeddings

    def __call__(self, **_):
        class Saida:
            pass

        saida= Saida()
        saida.logits_per_image= torch.tensor(self.logits, dtype=torch.float32)
        saida.image_embeds= torch.tensor(self.embeddings, dtype=torch.float32)
        return saida


def _logits(categoria, classe, forca= 10.0):
    config= CLASSES.categorias[categoria]
    itens= []
    for nome, descricao in config.descricoes.items():
        itens.extend([nome] * (1 if isinstance(descricao, str) else len(descricao)))
    itens.extend([None] * len(config.negativos))
    linha= [0.0] * len(itens)
    linha[itens.index(classe)]= forca
    return linha


def _cabeca():
    coef= np.array([[5.0, 0.0], [0.0, 5.0]])
    return Cabeca(["stop", "perigo"], coef, np.zeros(2))


def test_refinador_usa_a_cabeca_para_o_tipo_e_o_zero_shot_para_descartar():
    logits= [_logits("sinal", "cedencia"), _logits("sinal", None)]
    embeddings= [[1.0, 0.0], [1.0, 0.0]]
    refinador= Refinador(_Processador(), _Modelo(logits, embeddings), CLASSES, 0.5, cabecas={"sinal": _cabeca()})
    imagem= np.full((50, 50, 3), 100, np.uint8)
    (tipo, p_tipo), (lixo, _)= refinador.classificar("sinal", [imagem, imagem])
    assert tipo == "stop"
    assert p_tipo > 0.9
    assert lixo is None


def test_refinador_sem_cabeca_mantem_o_zero_shot():
    refinador= Refinador(_Processador(), _Modelo([_logits("sinal", "cedencia")], [[1.0, 0.0]]), CLASSES, 0.5)
    (tipo, _),= refinador.classificar("sinal", [np.full((50, 50, 3), 100, np.uint8)])
    assert tipo == "cedencia"


def test_cabeca_so_afeta_a_categoria_dela():
    logits= [_logits("residuos", "papeleira")]
    refinador= Refinador(_Processador(), _Modelo(logits, [[1.0, 0.0]]), CLASSES, 0.5, cabecas={"sinal": _cabeca()})
    (tipo, _),= refinador.classificar("residuos", [np.full((50, 50, 3), 100, np.uint8)])
    assert tipo == "papeleira"
