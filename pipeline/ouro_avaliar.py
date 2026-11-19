"""Scores a detector on the hand-reviewed gold set (see `pipeline.ouro`)."""

import argparse
import json
import sys
from argparse import Namespace
from collections import Counter
from pathlib import Path

import cv2

from pipeline.config import load_classes
from pipeline.errors import ErroPipeline

LIMIARES_RELATORIO= (0.1, 0.2, 0.3, 0.4, 0.5)
LIMIAR_IOU= 0.5
LIMIAR_PROPOSTA= 0.1
TAMANHOS= ((0, 24, "<24 px"), (24, 48, "24-48 px"), (48, 96, "48-96 px"), (96, 10**6, ">=96 px"))


def iou(a, b) -> float:
    largura= min(a[2], b[2]) - max(a[0], b[0])
    altura= min(a[3], b[3]) - max(a[1], b[1])
    if largura <= 0 or altura <= 0:
        return 0.0
    intersecao= largura * altura
    uniao= (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersecao
    return intersecao / uniao


def emparelhar(previstas: list[dict], ouro: list[dict], limiar_iou: float= LIMIAR_IOU):
    """One-to-one pairs (prediction index, gold index), most overlapping boxes first."""
    candidatos= sorted(
        (
            (iou(p["caixa"], g["caixa"]), i, j)
            for i, p in enumerate(previstas)
            for j, g in enumerate(ouro)
        ),
        reverse=True,
    )
    usadas_p, usadas_g, pares= set(), set(), []
    for valor, i, j in candidatos:
        if valor < limiar_iou:
            break
        if i in usadas_p or j in usadas_g:
            continue
        usadas_p.add(i)
        usadas_g.add(j)
        pares.append((i, j))
    return pares


def caixas_de_ouro(telas: dict) -> dict[str, list[dict]]:
    """Boxes the reviewer kept (accepted or corrected), only from reviewed images."""
    return {
        nome: [c for c in t["caixas"] if c["estado"] in ("aceite", "corrigido")]
        for nome, t in telas.items()
        if t["revista"]
    }


def medir(ouro: dict[str, list[dict]], previsoes: dict[str, list[dict]], limiar: float) -> dict:
    tp= fp= fn= certos= 0
    confusao= Counter()
    falsos= Counter()
    por_tamanho= {rotulo: [0, 0] for _, _, rotulo in TAMANHOS}
    for nome, gold in ouro.items():
        previstas= [p for p in previsoes.get(nome, []) if p["confianca"] >= limiar]
        pares= emparelhar(previstas, gold)
        achadas_p= {i for i, _ in pares}
        achadas_g= {j for _, j in pares}
        tp+= len(pares)
        fp+= len(previstas) - len(pares)
        fn+= len(gold) - len(pares)
        for i, p in enumerate(previstas):
            if i not in achadas_p:
                falsos[p["classe"]]+= 1
        for i, j in pares:
            confusao[(gold[j]["classe"], previstas[i]["classe"])]+= 1
            certos+= previstas[i]["classe"] == gold[j]["classe"]
        for j, g in enumerate(gold):
            altura= g["caixa"][3] - g["caixa"][1]
            for minimo, maximo, rotulo in TAMANHOS:
                if minimo <= altura < maximo:
                    por_tamanho[rotulo][1]+= 1
                    por_tamanho[rotulo][0]+= j in achadas_g
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tipo_certo": certos,
        "precisao": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "confusao": confusao,
        "falsos": falsos,
        "por_tamanho": por_tamanho,
    }


def _n(valor) -> str:
    return "n/a" if valor is None else f"{valor:.2f}"


def relatorio(ouro: dict, previsoes: dict, nome: str, limiar_destaque: float) -> str:
    n_ouro= sum(len(v) for v in ouro.values())
    linhas= [
        f"# Gold-set results: {nome}",
        "",
        f"{len(ouro)} reviewed images, {n_ouro} gold boxes, IoU >= {LIMIAR_IOU}.",
        "",
        "## Finding signs (any type)",
        "",
        "| Confidence >= | Found | False alarms | Missed | Precision | Recall | Type right when found |",
        "|---|---|---|---|---|---|---|",
    ]
    for limiar in LIMIARES_RELATORIO:
        m= medir(ouro, previsoes, limiar)
        tipo= f"{m['tipo_certo']}/{m['tp']} ({m['tipo_certo'] / m['tp']:.0%})" if m["tp"] else "n/a"
        marca= " (pipeline setting)" if limiar == limiar_destaque else ""
        linhas.append(
            f"| {limiar}{marca} | {m['tp']} | {m['fp']} | {m['fn']} | "
            f"{_n(m['precisao'])} | {_n(m['recall'])} | {tipo} |"
        )
    m= medir(ouro, previsoes, limiar_destaque)
    linhas+= [
        "",
        f"## By sign type at confidence >= {limiar_destaque}",
        "",
        "Type recall counts missed signs as wrong; type precision looks only at found signs.",
        "",
        "| Type | In gold set | Found | Type right | Type recall | Predicted as this type | Type precision | False alarms |",
        "|---|---|---|---|---|---|---|---|",
    ]
    classes= sorted(
        {c["classe"] for v in ouro.values() for c in v}
        | {p for _, p in m["confusao"]}
        | set(m["falsos"])
    )
    for classe in classes:
        no_ouro= sum(1 for v in ouro.values() for c in v if c["classe"] == classe)
        achadas= sum(n for (g, _), n in m["confusao"].items() if g == classe)
        certas= m["confusao"].get((classe, classe), 0)
        previstas= sum(n for (_, p), n in m["confusao"].items() if p == classe)
        linhas.append(
            f"| {classe} | {no_ouro} | {achadas} | {certas} | "
            f"{_n(certas / no_ouro if no_ouro else None)} | {previstas} | "
            f"{_n(certas / previstas if previstas else None)} | {m['falsos'].get(classe, 0)} |"
        )
    linhas+= [
        "",
        "## Recall by sign size (height of the box in the reviewed image)",
        "",
        "| Size | Gold boxes | Found | Recall |",
        "|---|---|---|---|",
    ]
    for _, _, rotulo in TAMANHOS:
        achadas, total= m["por_tamanho"][rotulo]
        linhas.append(f"| {rotulo} | {total} | {achadas} | {_n(achadas / total if total else None)} |")
    colunas= sorted({p for _, p in m["confusao"]})
    linhas+= [
        "",
        "## Type confusion among found signs (rows: your answer, columns: pipeline)",
        "",
        "| | " + " | ".join(colunas) + " |",
        "|---|" + "---|" * len(colunas),
    ]
    for g in sorted({g for g, _ in m["confusao"]}):
        celulas= " | ".join(str(m["confusao"].get((g, c), 0)) for c in colunas)
        linhas.append(f"| {g} | {celulas} |")
    return "\n".join(linhas)


def avaliar(args: argparse.Namespace) -> int:
    from pipeline.ouro import CATEGORIAS, FICHEIRO, _guardar_atomico
    from pipeline.run import _detetor

    saida= Path(args.saida)
    dados= json.loads((saida / FICHEIRO).read_text(encoding="utf-8"))
    ouro= caixas_de_ouro(dados["telas"])
    if not ouro:
        raise ErroPipeline("No reviewed images in the gold set yet")
    classes= load_classes(Path(args.classes))
    cache= saida / f"predictions_{args.nome}.json"
    if cache.exists() and not args.refazer:
        previsoes= json.loads(cache.read_text(encoding="utf-8"))
    else:
        detetor= _detetor(
            Namespace(
                detetor=args.detetor,
                pesos=args.pesos,
                limiar=LIMIAR_PROPOSTA,
                sem_refinar=args.sem_refinar,
                limiar_classe=0.3,
                cabeca_sinal=args.cabeca_sinal,
            ),
            classes,
            limiares=False,
        )
        previsoes= {}
        for n, nome in enumerate(ouro, 1):
            imagem= cv2.imread(str(saida / "imagens" / dados["telas"][nome]["imagem"]))
            previsoes[nome]= [
                {
                    "caixa": [round(v, 1) for v in d.bbox_xyxy],
                    "classe": d.class_name,
                    "confianca": round(d.confidence, 3),
                }
                for d in detetor.detect(nome, imagem)
                if d.category in dados.get("categorias", CATEGORIAS)
            ]
            if n % 25 == 0:
                print(f"[{n}/{len(ouro)}] images scored", file=sys.stderr, flush=True)
        _guardar_atomico(cache, previsoes)
    destaque= classes.categorias["sinal"].limiar_detecao
    texto= relatorio(ouro, previsoes, args.nome, destaque)
    (saida / f"results_{args.nome}.md").write_text(texto, encoding="utf-8")
    print(texto)
    return 0
