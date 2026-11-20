"""Trains the sign-type head with the web reference signs (training.datasets.sinais_web).

The reference images are clean drawings, so each one is turned into several street-like crops:
small, blurred (focus or motion), seen at an angle, partly hidden (pole, branch, car, another sign),
cut by the image border, faded, dark or overexposed, noisy and JPEG-compressed, on a real street
background. Those are embedded with CLIP together with the reviewed crops of the gold-set batches,
a logistic head is trained, and it is mixed with the current head (which knows real Mapillary signs).

    python -m training.tipos_web --lotes data/ouro_batch2 --destino data/treino/tipo_sinal_web.npz
"""

import argparse
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np

from pipeline.detect.cabeca import Cabeca, treinar
from training.tipos import LOTE, recortes_de

LADOS= (12, 16, 20, 24, 32, 44, 60, 90)
COPIAS= 16
REPETIR_REAIS= 10
COPIAS_REAIS= 10
REGULARIZACAO= 30.0
PESO_NOVA= 0.4
# Classes whose meaning did not change with the official categories: safe to take from batches
# labelled before them (where blue squares, direction plates, etc. may be in the old scheme).
ESTAVEIS= frozenset({"perigo", "cedencia", "stop", "proibicao", "limite_velocidade", "obrigacao", "semaforo"})
PENALIZACAO_NOVAS= 2.0


def _fundo(rng: random.Random, fundos: list[np.ndarray], altura: int, largura: int) -> np.ndarray:
    imagem= rng.choice(fundos)
    altura, largura= min(altura, imagem.shape[0]), min(largura, imagem.shape[1])
    y= rng.randrange(0, imagem.shape[0] - altura + 1)
    x= rng.randrange(0, imagem.shape[1] - largura + 1)
    return imagem[y : y + altura, x : x + largura].astype(np.float32)


def _perspetiva(rng: random.Random, rgba: np.ndarray) -> np.ndarray:
    altura, largura= rgba.shape[:2]
    origem= np.float32([[0, 0], [largura, 0], [largura, altura], [0, altura]])
    desvio= lambda escala: rng.uniform(-escala, escala)
    destino= origem + np.float32([[desvio(0.12 * largura), desvio(0.08 * altura)] for _ in range(4)])
    destino-= destino.min(axis=0)
    tamanho= (int(destino[:, 0].max()) + 1, int(destino[:, 1].max()) + 1)
    matriz= cv2.getPerspectiveTransform(origem, destino)
    return cv2.warpPerspective(rgba, matriz, tamanho, flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))


def _tapar(rng: random.Random, imagem: np.ndarray, fundos: list[np.ndarray]) -> None:
    """Something in front of the sign: a pole, a branch, a car or a patch of street."""
    altura, largura= imagem.shape[:2]
    tipo= rng.random()
    if tipo < 0.35:  # pole or lamp post, vertical
        grossura= max(1, int(largura * rng.uniform(0.08, 0.25)))
        x= rng.randrange(0, largura)
        cor= rng.choice([(40, 40, 40), (90, 90, 90), (160, 160, 160), (30, 60, 30)])
        cv2.rectangle(imagem, (x, 0), (x + grossura, altura), cor, -1)
    elif tipo < 0.6:  # branches and leaves
        for _ in range(rng.randint(2, 6)):
            p0= (rng.randrange(0, largura), rng.randrange(0, altura))
            p1= (rng.randrange(0, largura), rng.randrange(0, altura))
            cor= (rng.randint(10, 60), rng.randint(40, 110), rng.randint(10, 60))
            cv2.line(imagem, p0, p1, cor, max(1, int(largura * rng.uniform(0.03, 0.1))))
    else:  # a car, a person or another object: a piece of street covering a side
        fracao= rng.uniform(0.15, 0.5)
        if rng.random() < 0.5:
            h= int(altura * fracao)
            y= 0 if rng.random() < 0.3 else altura - h
            imagem[y : y + h]= _fundo(rng, fundos, h, largura)[: h, :largura]
        else:
            w= int(largura * fracao)
            x= 0 if rng.random() < 0.5 else largura - w
            imagem[:, x : x + w]= _fundo(rng, fundos, altura, w)[:altura, :w]


def _desfocar(rng: random.Random, imagem: np.ndarray) -> np.ndarray:
    if rng.random() < 0.5:
        sigma= rng.uniform(0.5, 2.5)
        return cv2.GaussianBlur(imagem, (0, 0), sigma)
    comprimento= rng.randint(3, 9)
    nucleo= np.zeros((comprimento, comprimento), np.float32)
    nucleo[comprimento // 2, :]= 1.0 / comprimento
    centro= (comprimento / 2 - 0.5, comprimento / 2 - 0.5)
    nucleo= cv2.warpAffine(nucleo, cv2.getRotationMatrix2D(centro, rng.uniform(0, 180), 1.0), (comprimento, comprimento))
    return cv2.filter2D(imagem, -1, nucleo / max(nucleo.sum(), 1e-6))


def aumentar(rng: random.Random, rgba: np.ndarray, fundos: list[np.ndarray]) -> np.ndarray:
    """One street-like BGR crop of a clean BGRA sign drawing."""
    sinal= _perspetiva(rng, rgba) if rng.random() < 0.7 else rgba
    if rng.random() < 0.3:
        centro= (sinal.shape[1] / 2, sinal.shape[0] / 2)
        rotacao= cv2.getRotationMatrix2D(centro, rng.uniform(-25, 25), 1.0)
        sinal= cv2.warpAffine(sinal, rotacao, sinal.shape[1::-1], borderValue=(0, 0, 0, 0))
    lado= rng.choice(LADOS)
    escala= lado / max(sinal.shape[:2])
    tamanho= (max(4, round(sinal.shape[1] * escala)), max(4, round(sinal.shape[0] * escala)))
    sinal= cv2.resize(sinal, tamanho, interpolation=cv2.INTER_AREA)
    altura, largura= sinal.shape[:2]
    margem= int(max(altura, largura) * 0.15) + 1
    tela= _fundo(rng, fundos, altura + 2 * margem, largura + 2 * margem)
    tela= cv2.resize(tela, (largura + 2 * margem, altura + 2 * margem))
    alfa= sinal[:, :, 3:4].astype(np.float32) / 255
    cor= sinal[:, :, :3].astype(np.float32)
    if rng.random() < 0.4:  # faded or dirty paint
        cinzento= cor.mean(axis=2, keepdims=True)
        cor= cor * (1 - rng.uniform(0.2, 0.6)) + cinzento * rng.uniform(0.2, 0.6)
    cor= cor * rng.uniform(0.35, 1.15) + rng.uniform(-35, 35)  # shade, dusk, sun
    regiao= tela[margem : margem + altura, margem : margem + largura]
    tela[margem : margem + altura, margem : margem + largura]= cor * alfa + regiao * (1 - alfa)
    return degradar(rng, np.clip(tela, 0, 255).astype(np.uint8), fundos)


def degradar(rng: random.Random, imagem: np.ndarray, fundos: list[np.ndarray]) -> np.ndarray:
    """What the street and the camera do to a sign crop: occlusion, border cut, blur, noise, JPEG."""
    imagem= imagem.copy()
    if rng.random() < 0.5:
        _tapar(rng, imagem, fundos)
    if rng.random() < 0.25:  # cut by the image border
        corte= rng.uniform(0.1, 0.35)
        lado_corte= rng.randrange(4)
        h, w= imagem.shape[:2]
        imagem= [
            imagem[int(h * corte) :],
            imagem[: h - int(h * corte)],
            imagem[:, int(w * corte) :],
            imagem[:, : w - int(w * corte)],
        ][lado_corte]
    if rng.random() < 0.7:
        imagem= _desfocar(rng, imagem)
    if rng.random() < 0.4:
        ruido= np.random.default_rng(rng.randrange(2**32)).normal(0, rng.uniform(3, 12), imagem.shape)
        imagem= np.clip(imagem.astype(np.float32) + ruido, 0, 255).astype(np.uint8)
    ok, codificada= cv2.imencode(".jpg", imagem, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(25, 90)])
    return cv2.imdecode(codificada, cv2.IMREAD_COLOR) if ok else imagem


def aumentar_real(rng: random.Random, recorte: np.ndarray, fundos: list[np.ndarray]) -> np.ndarray:
    """A reviewed street crop made harder: rotated, fewer pixels, darker or brighter, then degraded."""
    imagem= recorte
    if rng.random() < 0.5:
        altura, largura= imagem.shape[:2]
        rotacao= cv2.getRotationMatrix2D((largura / 2, altura / 2), rng.uniform(-25, 25), 1.0)
        imagem= cv2.warpAffine(imagem, rotacao, (largura, altura), borderMode=cv2.BORDER_REPLICATE)
    if rng.random() < 0.6:
        lado= rng.choice(LADOS)
        altura, largura= imagem.shape[:2]
        escala= lado / max(altura, largura)
        if escala < 1:
            pequeno= (max(2, round(largura * escala)), max(2, round(altura * escala)))
            imagem= cv2.resize(imagem, pequeno, interpolation=cv2.INTER_AREA)
    if rng.random() < 0.5:
        imagem= np.clip(imagem.astype(np.float32) * rng.uniform(0.35, 1.2) + rng.uniform(-25, 25), 0, 255).astype(np.uint8)
    return degradar(rng, imagem, fundos)


def ler_rgba(caminho: Path) -> np.ndarray:
    from PIL import Image

    return np.array(Image.open(caminho).convert("RGBA"))[:, :, [2, 1, 0, 3]].copy()


def recortes_revistos(pasta: Path) -> list[tuple[str, np.ndarray]]:
    dados= json.loads((pasta / "ouro.json").read_text(encoding="utf-8"))
    saida= []
    for tela in dados["telas"].values():
        if not tela["revista"]:
            continue
        largura, altura= tela["largura"], tela["altura"]
        itens= [
            {"caixa": [c["caixa"][0] / largura, c["caixa"][1] / altura, c["caixa"][2] / largura, c["caixa"][3] / altura],
             "classe": c["classe"]}
            for c in tela["caixas"]
            if c["estado"] in ("aceite", "corrigido")
        ]
        imagem= cv2.imread(str(pasta / "imagens" / tela["imagem"]))
        if imagem is not None:
            saida+= [(classe, recorte) for _, classe, recorte in recortes_de(imagem, itens, minimo=12)]
    return saida


def misturar(antiga: Cabeca, nova: Cabeca, peso: float= PESO_NOVA, penalizacao: float= PENALIZACAO_NOVAS) -> Cabeca:
    """Averages the logits of both heads; classes the old head lacks get its mean logit minus a penalty."""
    media_coef, media_inter= antiga.coef.mean(axis=0), antiga.intercepto.mean()
    coefs, inters= [], []
    for j, classe in enumerate(nova.classes):
        if classe in antiga.classes:
            i= antiga.classes.index(classe)
            coef, inter= antiga.coef[i], antiga.intercepto[i]
        else:
            coef, inter= media_coef, media_inter - penalizacao
        coefs.append((1 - peso) * coef + peso * nova.coef[j])
        inters.append((1 - peso) * inter + peso * nova.intercepto[j])
    return Cabeca(nova.classes, np.array(coefs), np.array(inters))


def _embeddings_de_treino(args: argparse.Namespace) -> tuple[np.ndarray | None, list[str] | None]:
    """Augmented web signs, the real crops repeated and their degraded copies, embedded with CLIP."""
    from training.tipos import _carregar_modelo

    rng= random.Random(args.semente)
    lotes= [Path(p) for p in args.lotes]
    fundos= [cv2.imread(str(p)) for lote in lotes for p in sorted((lote / "imagens").glob("*.jpg"))[:80]]
    fundos= [f for f in fundos if f is not None]
    if not fundos:
        print("Erro: sem imagens de fundo nos lotes", file=sys.stderr)
        return None, None
    raiz= Path(args.web)
    web= []
    for linha in (raiz / "manifesto.jsonl").read_text(encoding="utf-8").splitlines():
        item= json.loads(linha)
        rgba= ler_rgba(raiz / item["ficheiro"])
        web+= [(item["classe"], aumentar(rng, rgba, fundos)) for _ in range(args.copias_web)]
    if args.exemplos:
        amostra= [cv2.resize(r, (96, 96)) for _, r in rng.sample(web, 48)]
        cv2.imwrite(args.exemplos, np.vstack([np.hstack(amostra[i : i + 12]) for i in range(0, 48, 12)]))
    reais= [r for lote in lotes for r in recortes_revistos(lote)]
    reais+= [
        (classe, recorte)
        for lote in args.lotes_parciais
        for classe, recorte in recortes_revistos(Path(lote))
        if classe in ESTAVEIS
    ]
    incorporar, _= _carregar_modelo(argparse.Namespace(classes=args.classes))

    def embeddings(itens):
        return np.vstack([incorporar([r for _, r in itens[i : i + LOTE]]) for i in range(0, len(itens), LOTE)])

    X_reais= embeddings(reais)
    aumentados= [(c, aumentar_real(rng, r, fundos)) for c, r in reais for _ in range(args.copias_reais)]
    partes= [embeddings(web)] + [X_reais] * REPETIR_REAIS + ([embeddings(aumentados)] if aumentados else [])
    X= np.vstack(partes)
    y= [c for c, _ in web] + [c for c, _ in reais] * REPETIR_REAIS + [c for c, _ in aumentados]
    return X, y


def main(argv: list[str] | None= None) -> int:
    parser= argparse.ArgumentParser(prog="python -m training.tipos_web")
    parser.add_argument("--web", default="data/datasets/sinais_web")
    parser.add_argument("--lotes", nargs="*", default=["data/ouro_batch2"], help="reviewed batches (never the test set)")
    parser.add_argument(
        "--lotes-parciais",
        nargs="*",
        default=[],
        help="batches labelled before the official categories: only their stable classes are used",
    )
    parser.add_argument("--antiga", help="head to mix the new one with; without it the new head is saved alone")
    parser.add_argument("--destino", default="data/treino/tipo_sinal_web.npz")
    parser.add_argument("--classes", default="config/classes.yaml")
    parser.add_argument("--exemplos", help="save a sheet of augmented crops here, to look at")
    parser.add_argument("--semente", type=int, default=0)
    parser.add_argument("--copias-reais", type=int, default=COPIAS_REAIS, help="degraded copies of each real crop")
    parser.add_argument("--copias-web", type=int, default=COPIAS, help="augmented copies of each web sign")
    parser.add_argument("--peso", type=float, default=PESO_NOVA, help="weight of the new head in the mix (1 = new only)")
    parser.add_argument("--cache", help="npz with the embeddings: read if it exists, written otherwise")
    args= parser.parse_args(argv)
    cache= Path(args.cache) if args.cache else None
    if cache is not None and cache.exists():
        guardado= np.load(cache)
        X, y= guardado["X"], [str(c) for c in guardado["y"]]
    else:
        X, y= _embeddings_de_treino(args)
        if X is None:
            return 1
        if cache is not None:
            np.savez(cache, X=X, y=np.array(y))
    nova= treinar(X, y, REGULARIZACAO)
    final= misturar(Cabeca.carregar(Path(args.antiga)), nova, args.peso) if args.antiga else nova
    final.guardar(Path(args.destino))
    print(f"{len(y)} exemplos; classes: {', '.join(final.classes)}")
    print(f"Cabeça guardada em {args.destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
