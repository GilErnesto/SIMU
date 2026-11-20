import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

import cv2

from pipeline.detect.panorama import FOV_VISTA, LADO_VISTA, views
from pipeline.detect.refinar import LADO_MINIMO, MARGEM
from training.datasets.openimages import NOMES
from training.datasets.yolo import escrever_data_yaml, guardar_exemplo

BASE_PADRAO= Path("data/avaliacao")
CELULA_GRAUS= 0.001
FRACAO_VAL= 5
CONFIANCA_PSEUDO= 0.5
LADO_MAX= 4096
CLASSE_LUZ= NOMES.index("candeeiro")
LUZ_YOLO= {"poste_luz", "candeeiro"}
DELTA_MAX_GRAUS= 80.0
VISIVEL_MIN= 0.5
LADO_VISIVEL_MIN= 4.0
VISTAS_VAZIAS_UMA_EM= 4


def identidade(imagem):
    return imagem


def divisao_de(registo: dict, reservado: bool) -> str:
    if reservado:
        return "val"
    lat, lon= registo.get("lat"), registo.get("lon")
    if lat is None or lon is None:
        chave= str(registo["id"])
    else:
        chave= f"{round(lat / CELULA_GRAUS)}:{round(lon / CELULA_GRAUS)}"
    return "val" if int(hashlib.md5(chave.encode()).hexdigest(), 16) % FRACAO_VAL == 0 else "train"


def ler_rotulos(base: Path, lote: str) -> dict[str, dict]:
    ficheiro= base / "rotulos" / f"{lote}.jsonl"
    resultado= {}
    with ficheiro.open(encoding="utf-8") as linhas:
        for linha in linhas:
            try:
                registo= json.loads(linha)
                resultado[str(registo["id"])]= registo
            except (ValueError, KeyError):
                continue
    return resultado


def ler_pseudo(base: Path, lote: str) -> dict[str, list[tuple[int, list[float]]]]:
    resultado= {}
    with (base / lote / "deteccoes.jsonl").open(encoding="utf-8") as linhas:
        for linha in linhas:
            try:
                registo= json.loads(linha)
                id_fonte= str(registo["imagem"]["id_fonte"])
            except (ValueError, KeyError):
                continue
            itens= []
            for d in registo.get("deteccoes", []):
                if d.get("confidence", 0) < CONFIANCA_PSEUDO:
                    continue
                if d.get("category") == "sinal":
                    itens.append((NOMES.index("semaforo" if d.get("class_name") == "semaforo" else "outro"), d["bbox_xyxy"]))
                elif d.get("category") == "residuos":
                    itens.append((NOMES.index("contentor"), d["bbox_xyxy"]))
            resultado[id_fonte]= itens
    return resultado


def recortar(imagem, bbox: list[float]):
    altura, largura= imagem.shape[:2]
    x0, y0, x1, y1= bbox
    mx, my= (x1 - x0) * MARGEM, (y1 - y0) * MARGEM
    a, b= max(0, int(x0 - mx)), max(0, int(y0 - my))
    c, d= min(largura, int(x1 + mx)), min(altura, int(y1 + my))
    if c - a < LADO_MINIMO or d - b < LADO_MINIMO:
        return None
    return imagem[b:d, a:c]


def caixa_na_vista(
    caixa: tuple[float, float, float, float],
    yaw: float,
    largura: int,
    altura: int,
    lado: int= LADO_VISTA,
) -> tuple[float, float, float, float] | None:
    x0, y0, x1, y1= caixa
    focal= lado / 2 / math.tan(math.radians(FOV_VISTA / 2))
    us= []
    for x in (x0, x1):
        phi= (x / largura - 0.5) * 360.0
        delta= (phi - yaw + 180.0) % 360.0 - 180.0
        if abs(delta) >= DELTA_MAX_GRAUS:
            return None
        us.append(lado / 2 + focal * math.tan(math.radians(delta)))
    vs= []
    for u in us:
        for y in (y0, y1):
            gama= (0.5 - min(max(y, 1.0), altura - 1.0) / altura) * math.pi
            vs.append(lado / 2 - math.tan(gama) * math.hypot(u - lado / 2, focal))
    a, b, c, d= min(us), min(vs), max(us), max(vs)
    area= (c - a) * (d - b)
    a, b, c, d= max(a, 0.0), max(b, 0.0), min(c, float(lado)), min(d, float(lado))
    if c - a < LADO_VISIVEL_MIN or d - b < LADO_VISIVEL_MIN or area <= 0:
        return None
    if (c - a) * (d - b) / area < VISIVEL_MIN:
        return None
    return a, b, c, d


def caixas_da_imagem(registo: dict, pseudo: list[tuple[int, list[float]]]) -> list[tuple[int, list[float]]]:
    luzes= [(CLASSE_LUZ, c["bbox"]) for c in registo["caixas"] if c["classe"] in LUZ_YOLO]
    return luzes + list(pseudo)


def exportar_recortes(imagem, registo: dict, lote: str, id_fonte: str, divisao: str, saida: Path, contagem: Counter) -> None:
    for n, caixa in enumerate(registo["caixas"]):
        recorte= recortar(imagem, caixa["bbox"])
        if recorte is None:
            contagem["recorte_pequeno"]+= 1
            continue
        pasta= saida / "recortes" / divisao / caixa["classe"]
        pasta.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(pasta / f"{lote}_{id_fonte}_{n}.jpg"), recorte, [cv2.IMWRITE_JPEG_QUALITY, 92])
        contagem[f"recorte_{divisao}_{caixa['classe']}"]+= 1


def exportar_panorama(imagem, caixas: list[tuple[int, list[float]]], lote: str, id_fonte: str, divisao: str, saida: Path, contagem: Counter) -> None:
    altura, largura= imagem.shape[:2]
    for yaw, vista in views(imagem, LADO_VISTA):
        mapeadas= []
        for indice, bbox in caixas:
            na_vista= caixa_na_vista(tuple(bbox), yaw, largura, altura, LADO_VISTA)
            if na_vista is not None:
                mapeadas.append((indice, *(v / LADO_VISTA for v in na_vista)))
        nome= f"{lote}_{id_fonte}_v{int(yaw)}"
        vazia_aceite= int(hashlib.md5(nome.encode()).hexdigest(), 16) % VISTAS_VAZIAS_UMA_EM == 0
        if not mapeadas and not vazia_aceite:
            contagem["vista_vazia_ignorada"]+= 1
            continue
        guardar_exemplo(saida, divisao, nome, vista, mapeadas, identidade, LADO_MAX)
        contagem[f"yolo_vista_{divisao}"]+= 1
        contagem[f"luzes_em_vistas_{divisao}"]+= sum(1 for m in mapeadas if m[0] == CLASSE_LUZ)


def exportar(
    base: Path,
    lotes: list[str],
    reservados: set[str],
    saida: Path,
    limites: dict[str, int] | None= None,
) -> Counter:
    contagem= Counter()
    limites= limites or {}
    for lote in lotes:
        rotulos= ler_rotulos(base, lote)
        pseudo= ler_pseudo(base, lote)
        for posicao, (id_fonte, registo) in enumerate(rotulos.items()):
            if posicao >= limites.get(lote, len(rotulos)):
                contagem["imagem_fora_do_limite"]+= 1
                continue
            imagem= cv2.imread(str(base / "imagens" / f"mapillary_{id_fonte}.jpg"))
            if imagem is None:
                contagem["imagem_em_falta"]+= 1
                continue
            divisao= divisao_de(registo, lote in reservados)
            exportar_recortes(imagem, registo, lote, id_fonte, divisao, saida, contagem)
            caixas= caixas_da_imagem(registo, pseudo.get(id_fonte, []))
            if registo.get("camera_type") == "spherical":
                exportar_panorama(imagem, caixas, lote, id_fonte, divisao, saida, contagem)
                contagem["panoramas"]+= 1
                continue
            altura, largura= imagem.shape[:2]
            normalizadas= [(i, b[0] / largura, b[1] / altura, b[2] / largura, b[3] / altura) for i, b in caixas]
            guardar_exemplo(saida, divisao, f"{lote}_{id_fonte}", imagem, normalizadas, identidade, LADO_MAX)
            contagem[f"yolo_{divisao}"]+= 1
    return contagem


def ler_limites(valores: list[str]) -> dict[str, int]:
    limites= {}
    for valor in valores:
        lote, _, numero= valor.partition(":")
        limites[lote]= int(numero)
    return limites


def main(argv: list[str] | None= None) -> int:
    parser= argparse.ArgumentParser(description="Exporta rótulos de luzes para YOLO e para a cabeça do CLIP")
    parser.add_argument("--lotes", nargs="+", required=True)
    parser.add_argument("--reservar", nargs="*", default=[], help="lotes só para validação")
    parser.add_argument("--limite", nargs="*", default=[], help="lote:N, usa só as primeiras N imagens rotuladas")
    parser.add_argument("--base", default=str(BASE_PADRAO))
    parser.add_argument("--saida", default="data/datasets/luz_aveiro")
    args= parser.parse_args(argv)
    saida= Path(args.saida)
    contagem= exportar(Path(args.base), args.lotes, set(args.reservar), saida, ler_limites(args.limite))
    escrever_data_yaml(saida, NOMES)
    for chave in sorted(contagem):
        print(f"{chave}: {contagem[chave]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
