from collections.abc import Collection
from pathlib import Path

import numpy as np

from pipeline.errors import ErroPipeline, ModeloEmFalta


class Cabeca:
    def __init__(self, classes: list[str], coef: np.ndarray, intercepto: np.ndarray):
        if coef.shape[0] != len(classes) or intercepto.shape != (len(classes),):
            raise ErroPipeline("Cabeça de classificação com formas incoerentes")
        self.classes= list(classes)
        self.coef= coef.astype(np.float32)
        self.intercepto= intercepto.astype(np.float32)

    def probabilidades(self, embeddings: np.ndarray) -> np.ndarray:
        logits= embeddings.astype(np.float32) @ self.coef.T + self.intercepto
        logits-= logits.max(axis=1, keepdims=True)
        exps= np.exp(logits)
        return exps / exps.sum(axis=1, keepdims=True)

    def prever(self, embeddings: np.ndarray, excluir: list[Collection[str]] | None= None) -> list[tuple[str, float]]:
        """excluir: per row, classes the head may not answer (the rest is renormalised)."""
        probabilidades= self.probabilidades(embeddings)
        for linha, proibidas in zip(probabilidades, excluir or [], strict=False):
            for classe in proibidas:
                if classe in self.classes:
                    linha[self.classes.index(classe)]= 0.0
            total= linha.sum()
            if total > 0:
                linha/= total
        melhores= probabilidades.argmax(axis=1)
        return [(self.classes[i], float(p[i])) for i, p in zip(melhores, probabilidades, strict=True)]

    def guardar(self, caminho: Path) -> None:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        np.savez(caminho, classes=np.array(self.classes), coef=self.coef, intercepto=self.intercepto)

    @classmethod
    def carregar(cls, caminho: Path) -> "Cabeca":
        if not caminho.exists():
            raise ModeloEmFalta(f"Cabeça de classificação em falta: {caminho}")
        dados= np.load(caminho, allow_pickle=False)
        return cls([str(c) for c in dados["classes"]], dados["coef"], dados["intercepto"])


def treinar(embeddings: np.ndarray, etiquetas: list[str], regularizacao: float= 1.0) -> Cabeca:
    from sklearn.linear_model import LogisticRegression

    if len(set(etiquetas)) < 2:
        raise ErroPipeline("São precisas pelo menos duas classes para treinar")
    modelo= LogisticRegression(C=regularizacao, max_iter=2000, class_weight="balanced")
    modelo.fit(embeddings, etiquetas)
    coef= modelo.coef_
    intercepto= modelo.intercept_
    if coef.shape[0] == 1:
        coef= np.vstack([-coef[0] / 2, coef[0] / 2])
        intercepto= np.array([-intercepto[0] / 2, intercepto[0] / 2])
    return Cabeca([str(c) for c in modelo.classes_], coef, intercepto)
