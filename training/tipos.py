import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from pipeline.detect.cabeca import treinar
from pipeline.detect.refinar import MARGEM
from pipeline.errors import ErroPipeline
from training.datasets.yolo import reduzir

LADO_ANONIMIZAR= 2048
LADO_MINIMO_PX= 24
MINIMO_POR_CLASSE= 15
QUALIDADE_JPEG= 92
LOTE= 32


def divisao_de(id_fonte: str) -> str:
    resumo= hashlib.md5(id_fonte.encode()).hexdigest()
    return "val" if int(resumo[:8], 16) % 5 == 0 else "train"


def recortes_de(imagem: np.ndarray, itens: list[dict], margem: float= MARGEM, minimo: int= LADO_MINIMO_PX):
    altura, largura= imagem.shape[:2]
    saida= []
    for n, item in enumerate(itens):
        x0, y0, x1, y1= item["caixa"]
        mx, my= (x1 - x0) * largura * margem, (y1 - y0) * altura * margem
        a, b= max(int(x0 * largura - mx), 0), max(int(y0 * altura - my), 0)
        c, d= min(int(x1 * largura + mx), largura), min(int(y1 * altura + my), altura)
        if min(c - a, d - b) < minimo:
            continue
        saida.append((n, item["classe"], imagem[b:d, a:c]))
    return saida


def recortar(
    ficheiro: Path, pasta_raw: Path, saida: Path, anonimizador, saida_log=sys.stderr
) -> Counter:
    contagem= Counter()
    linhas= ficheiro.read_text(encoding="utf-8").splitlines()
    for numero, linha in enumerate(linhas, 1):
        try:
            dados= json.loads(linha)
        except json.JSONDecodeError:
            continue
        caminho= pasta_raw / f"{dados['id_fonte']}.jpg"
        if not caminho.exists():
            continue
        imagem= cv2.imread(str(caminho))
        if imagem is None:
            continue
        anonima= anonimizador(reduzir(imagem, LADO_ANONIMIZAR))
        del imagem
        for n, classe, recorte in recortes_de(anonima, dados["itens"]):
            destino= saida / "recortes" / divisao_de(dados["id_fonte"]) / classe
            destino.mkdir(parents=True, exist_ok=True)
            if not cv2.imwrite(str(destino / f"{dados['id_fonte']}_{n}.jpg"), recorte, [cv2.IMWRITE_JPEG_QUALITY, QUALIDADE_JPEG]):
                raise OSError(f"Não foi possível gravar um recorte de {dados['id_fonte']}")
            contagem[classe]+= 1
        caminho.unlink()
        if numero % 100 == 0:
            print(f"[{numero}/{len(linhas)}] {sum(contagem.values())} recortes", file=saida_log, flush=True)
    return contagem


def listar(saida: Path) -> dict[str, list[tuple[Path, str]]]:
    return {
        divisao: [(f, f.parent.name) for f in sorted((saida / "recortes" / divisao).glob("*/*.jpg"))]
        for divisao in ("train", "val")
    }


def incorporar_tudo(ficheiros: list[Path], incorporar) -> np.ndarray:
    blocos= []
    for i in range(0, len(ficheiros), LOTE):
        imagens= [cv2.imread(str(f)) for f in ficheiros[i : i + LOTE]]
        blocos.append(incorporar([im for im in imagens if im is not None]))
    return np.vstack(blocos)


def avaliar(previstas: list[str], reais: list[str]) -> dict:
    classes= sorted(set(reais) | set(previstas))
    por_classe= {}
    for classe in classes:
        tp= sum(1 for p, r in zip(previstas, reais, strict=True) if p == r == classe)
        fp= sum(1 for p, r in zip(previstas, reais, strict=True) if p == classe and r != classe)
        fn= sum(1 for p, r in zip(previstas, reais, strict=True) if r == classe and p != classe)
        por_classe[classe]= {
            "exemplos": tp + fn,
            "precisao": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
        }
    certos= sum(1 for p, r in zip(previstas, reais, strict=True) if p == r)
    return {"exatidao": certos / len(reais) if reais else None, "classes": por_classe}


def treinar_tipos(saida: Path, incorporar, zero_shot, destino: Path) -> dict:
    listados= listar(saida)
    contagem= Counter(classe for _, classe in listados["train"])
    usadas= {c for c, n in contagem.items() if n >= MINIMO_POR_CLASSE}
    if len(usadas) < 2:
        raise ErroPipeline(f"Poucos exemplos: {dict(contagem)}")
    treino= [(f, c) for f, c in listados["train"] if c in usadas]
    validacao= [(f, c) for f, c in listados["val"] if c in usadas]
    X_treino= incorporar_tudo([f for f, _ in treino], incorporar)
    cabeca= treinar(X_treino, [c for _, c in treino])
    relatorio= {"classes_usadas": sorted(usadas), "treino": len(treino), "validacao": len(validacao)}
    if validacao:
        X_val= incorporar_tudo([f for f, _ in validacao], incorporar)
        reais= [c for _, c in validacao]
        relatorio["cabeca"]= avaliar([c for c, _ in cabeca.prever(X_val)], reais)
        relatorio["zero_shot"]= avaliar(zero_shot([f for f, _ in validacao]), reais)
    todos= treino + validacao
    final= treinar(incorporar_tudo([f for f, _ in todos], incorporar), [c for _, c in todos])
    final.guardar(destino)
    return relatorio


def _carregar_modelo(args, categoria):
    from pipeline.config import load_classes
    from pipeline.detect.refinar import Refinador

    classes= load_classes(Path(args.classes))
    refinador= Refinador.load(classes)
    import torch

    def incorporar(recortes):
        imagens= [cv2.cvtColor(r, cv2.COLOR_BGR2RGB) for r in recortes]
        entradas= refinador.processor(text=["a"], images=imagens, return_tensors="pt", padding=True).to(refinador.dispositivo)
        with torch.no_grad():
            return refinador.modelo(**entradas).image_embeds.cpu().numpy()

    def zero_shot(ficheiros):
        previstas= []
        for i in range(0, len(ficheiros), LOTE):
            recortes= [cv2.imread(str(f)) for f in ficheiros[i : i + LOTE]]
            for classe, _ in refinador.classificar(categoria, recortes):
                previstas.append(classe or "negativo")
        return previstas

    return incorporar, zero_shot


def main(argv: list[str] | None= None) -> int:
    parser= argparse.ArgumentParser(prog="python -m training.tipos")
    parser.add_argument("fase", choices=("recortar", "treinar"))
    parser.add_argument("--saida", default="data/datasets/tipos")
    parser.add_argument("--raw", default="data/raw/tipos_mapillary")
    parser.add_argument("--egoblur", default="models/egoblur")
    parser.add_argument("--classes", default="config/classes.yaml")
    parser.add_argument("--destino", default="models/tipo_sinal.npz")
    parser.add_argument("--categoria", default="sinal")
    args= parser.parse_args(argv)
    saida= Path(args.saida)
    try:
        if args.fase == "recortar":
            from pipeline.anonymize.egoblur import Anonymizer

            contagem= recortar(saida / "detecoes.jsonl", Path(args.raw), saida, Anonymizer.from_dir(Path(args.egoblur)))
            print(f"Recortes novos: {dict(contagem)}")
        else:
            incorporar, zero_shot= _carregar_modelo(args, args.categoria)
            relatorio= treinar_tipos(saida, incorporar, zero_shot, Path(args.destino))
            (saida / "relatorio.json").write_text(json.dumps(relatorio, indent=1, ensure_ascii=False), encoding="utf-8")
            print(json.dumps(relatorio, indent=1, ensure_ascii=False))
    except (ErroPipeline, OSError, FileNotFoundError) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
