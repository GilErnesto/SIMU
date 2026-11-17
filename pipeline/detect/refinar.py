import math
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

from pipeline.config import Classes
from pipeline.detect.cabeca import Cabeca
from pipeline.models import Detection

MODELO_PADRAO= "openai/clip-vit-large-patch14"
LIMIAR_CLASSE= 0.5
MARGEM= 0.15
LADO_MINIMO= 12


def recortar(image: np.ndarray, caixa: tuple[float, float, float, float]) -> np.ndarray | None:
    altura, largura= image.shape[:2]
    x1, y1, x2, y2= caixa
    mx, my= (x2 - x1) * MARGEM, (y2 - y1) * MARGEM
    x1, y1= max(int(x1 - mx), 0), max(int(y1 - my), 0)
    x2, y2= min(int(x2 + mx), largura), min(int(y2 + my), altura)
    if x2 - x1 < LADO_MINIMO or y2 - y1 < LADO_MINIMO:
        return None
    return image[y1:y2, x1:x2]


def _opcoes(categoria) -> tuple[list[str | None], list[str]]:
    ids= []
    textos= []
    for classe, descricao in categoria.descricoes.items():
        for texto in [descricao] if isinstance(descricao, str) else descricao:
            ids.append(classe)
            textos.append(f"a photo of {texto}")
    for texto in categoria.negativos:
        ids.append(None)
        textos.append(f"a photo of {texto}")
    return ids, textos


class Refinador:
    def __init__(
        self,
        processor,
        modelo,
        classes: Classes,
        limiar: float= LIMIAR_CLASSE,
        dispositivo: str= "cpu",
        cabecas: dict[str, Cabeca] | None= None,
    ):
        self.processor= processor
        self.modelo= modelo
        self.limiar= limiar
        self.dispositivo= dispositivo
        self.cabecas= cabecas or {}
        self.opcoes= {
            categoria.nome: _opcoes(categoria)
            for categoria in classes.categorias.values()
            if categoria.descricoes
        }

    @classmethod
    def load(
        cls,
        classes: Classes,
        nome: str= MODELO_PADRAO,
        limiar: float= LIMIAR_CLASSE,
        cabecas: dict[str, Path] | None= None,
    ) -> "Refinador":
        import torch
        from transformers import CLIPModel, CLIPProcessor

        dispositivo= "cuda" if torch.cuda.is_available() else "cpu"
        processor= CLIPProcessor.from_pretrained(nome)
        modelo= CLIPModel.from_pretrained(nome).to(dispositivo).eval()
        carregadas= {categoria: Cabeca.carregar(caminho) for categoria, caminho in (cabecas or {}).items()}
        return cls(processor, modelo, classes, limiar, dispositivo, carregadas)

    def classificar(self, categoria: str, recortes: list[np.ndarray]) -> list[tuple[str | None, float]]:
        import torch

        ids, textos= self.opcoes[categoria]
        imagens= [cv2.cvtColor(r, cv2.COLOR_BGR2RGB) for r in recortes]
        entradas= self.processor(text=textos, images=imagens, return_tensors="pt", padding=True)
        entradas= entradas.to(self.dispositivo)
        with torch.no_grad():
            saida= self.modelo(**entradas)
        probabilidades= saida.logits_per_image.softmax(dim=-1).cpu().tolist()
        cabeca= self.cabecas.get(categoria)
        tipos= cabeca.prever(saida.image_embeds.cpu().numpy()) if cabeca is not None else None
        previstas= []
        for i, linha in enumerate(probabilidades):
            somas= defaultdict(float)
            for classe, probabilidade in zip(ids, linha, strict=True):
                somas[classe]+= probabilidade
            melhor= max(somas, key=somas.get)
            if tipos is not None and melhor is not None:
                previstas.append(tipos[i])
            else:
                previstas.append((melhor, somas[melhor]))
        return previstas


class DuasFases:
    def __init__(self, detetor, refinador: Refinador, classes: Classes):
        self.detetor= detetor
        self.refinador= refinador
        self.classes= classes

    def detect(self, image_id: str, image: np.ndarray) -> list[Detection]:
        detecoes= self.detetor.detect(image_id, image)
        por_categoria= defaultdict(list)
        for posicao, detecao in enumerate(detecoes):
            categoria= self.classes.categorias[detecao.category]
            if detecao.class_name in (*categoria.gerais, *categoria.descricoes):
                recorte= recortar(image, detecao.bbox_xyxy)
                if recorte is not None:
                    por_categoria[detecao.category].append((posicao, recorte))
        resultado= list(detecoes)
        descartadas= set()
        for categoria, itens in por_categoria.items():
            previstas= self.refinador.classificar(categoria, [recorte for _, recorte in itens])
            for (posicao, _), (classe, probabilidade) in zip(itens, previstas, strict=True):
                if probabilidade < self.refinador.limiar:
                    continue
                if classe is None:
                    descartadas.add(posicao)
                    continue
                original= detecoes[posicao]
                resultado[posicao]= replace(
                    original,
                    class_name=classe,
                    confidence=math.sqrt(original.confidence * probabilidade),
                )
        return [d for posicao, d in enumerate(resultado) if posicao not in descartadas]
