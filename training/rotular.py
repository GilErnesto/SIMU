import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

BASE= Path(os.environ.get("AVALIACAO_DIR", "data/avaliacao"))
CATEGORIA= "iluminacao"
CONFIANCA_MIN= 0.3
INCERTEZA_MAX= 0.6
MAX_CAIXAS= 200
LADO_MIN= 2.0
PAGINA= Path(__file__).with_name("rotular.html")
LOTE_RE= re.compile(r"^[a-z0-9_]+$")
ID_RE= re.compile(r"^[0-9]+$")
trinco= threading.Lock()

app= FastAPI(title="Rotular luzes")


class Caixa(BaseModel):
    bbox: list[float] = Field(min_length=4, max_length=4)
    classe: Literal["poste_luz", "candeeiro", "nao_luz", "poste_eletrico"]
    origem: Literal["modelo", "manual"]
    auto: bool= False


class Rotulos(BaseModel):
    caixas: list[Caixa] = Field(max_length=MAX_CAIXAS)


def pasta_lote(lote: str) -> Path:
    if not LOTE_RE.match(lote):
        raise HTTPException(404, "Lote inválido")
    pasta= BASE / lote
    if not (pasta / "deteccoes.jsonl").is_file():
        raise HTTPException(404, "Lote não encontrado")
    return pasta


def validar_id(id_fonte: str) -> str:
    if not ID_RE.match(id_fonte):
        raise HTTPException(404, "Imagem inválida")
    return id_fonte


def ficheiro_imagem(id_fonte: str) -> Path:
    return BASE / "imagens" / f"mapillary_{id_fonte}.jpg"


def ficheiro_rotulos(lote: str) -> Path:
    return BASE / "rotulos" / f"{lote}.jsonl"


def ler_deteccoes(lote: str) -> dict[str, dict]:
    resultado= {}
    with (pasta_lote(lote) / "deteccoes.jsonl").open(encoding="utf-8") as ficheiro:
        for linha in ficheiro:
            try:
                registo= json.loads(linha)
                imagem= registo["imagem"]
                id_fonte= str(imagem["id_fonte"])
            except (ValueError, KeyError, TypeError):
                continue
            luzes= [
                {"bbox": d["bbox_xyxy"], "confianca": d["confidence"]}
                for d in registo.get("deteccoes", [])
                if d.get("category") == CATEGORIA and d.get("confidence", 0) >= CONFIANCA_MIN
            ]
            resultado[id_fonte]= {
                "id": id_fonte,
                "width": imagem.get("width"),
                "height": imagem.get("height"),
                "camera_type": imagem.get("camera_type"),
                "lat": imagem.get("lat"),
                "lon": imagem.get("lon"),
                "deteccoes": luzes,
            }
    return resultado


def ler_rotulos(lote: str) -> dict[str, dict]:
    ficheiro= ficheiro_rotulos(lote)
    resultado= {}
    if not ficheiro.is_file():
        return resultado
    with ficheiro.open(encoding="utf-8") as linhas:
        for linha in linhas:
            try:
                registo= json.loads(linha)
                resultado[str(registo["id"])]= registo
            except (ValueError, KeyError, TypeError):
                continue
    return resultado


def chave(id_fonte: str) -> str:
    return hashlib.sha1(id_fonte.encode()).hexdigest()


def construir_fila(imagens: dict[str, dict]) -> list[dict]:
    existentes= sorted((i for i in imagens if ficheiro_imagem(i).is_file()), key=chave)
    aleatorias= existentes[: (len(existentes) + 1) // 2]
    sorteadas= set(aleatorias)
    incertas= [
        i
        for i in existentes
        if i not in sorteadas and any(d["confianca"] < INCERTEZA_MAX for d in imagens[i]["deteccoes"])
    ]
    fila= []
    for k in range(max(len(incertas), len(aleatorias))):
        if k < len(incertas):
            fila.append({"id": incertas[k], "origem": "incerteza"})
        if k < len(aleatorias):
            fila.append({"id": aleatorias[k], "origem": "aleatoria"})
    return fila


@app.get("/favicon.ico", include_in_schema=False)
def icone():
    return Response(status_code=204)


@app.get("/")
def pagina():
    return FileResponse(PAGINA, media_type="text/html")


@app.get("/api/lotes")
def lotes():
    saida= []
    if not BASE.is_dir():
        return saida
    for pasta in sorted(BASE.iterdir()):
        if LOTE_RE.match(pasta.name) and (pasta / "deteccoes.jsonl").is_file():
            saida.append({"lote": pasta.name, "feitas": len(ler_rotulos(pasta.name))})
    return saida


@app.get("/api/lotes/{lote}/fila")
def fila(lote: str):
    imagens= ler_deteccoes(lote)
    feitas= ler_rotulos(lote)
    itens= construir_fila(imagens)
    for item in itens:
        item["feito"]= item["id"] in feitas
        item["n_det"]= len(imagens[item["id"]]["deteccoes"])
    return itens


@app.get("/api/lotes/{lote}/imagens/{id_fonte}")
def imagem(lote: str, id_fonte: str):
    id_fonte= validar_id(id_fonte)
    imagens= ler_deteccoes(lote)
    if id_fonte not in imagens or not ficheiro_imagem(id_fonte).is_file():
        raise HTTPException(404, "Imagem não encontrada")
    dados= dict(imagens[id_fonte])
    guardado= ler_rotulos(lote).get(id_fonte)
    dados["caixas"]= guardado["caixas"] if guardado else None
    return dados


@app.get("/api/lotes/{lote}/imagens/{id_fonte}/jpg")
def jpg(lote: str, id_fonte: str):
    pasta_lote(lote)
    ficheiro= ficheiro_imagem(validar_id(id_fonte))
    if not ficheiro.is_file():
        raise HTTPException(404, "Imagem não encontrada")
    return FileResponse(ficheiro, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})


@app.post("/api/lotes/{lote}/imagens/{id_fonte}")
def gravar(lote: str, id_fonte: str, pedido: Rotulos):
    id_fonte= validar_id(id_fonte)
    imagens= ler_deteccoes(lote)
    if id_fonte not in imagens:
        raise HTTPException(404, "Imagem não encontrada")
    dados= imagens[id_fonte]
    largura, altura= dados["width"], dados["height"]
    for caixa in pedido.caixas:
        x0, y0, x1, y1= caixa.bbox
        if not (0 <= x0 < x1 <= largura and 0 <= y0 < y1 <= altura):
            raise HTTPException(422, "Caixa fora da imagem")
        if x1 - x0 < LADO_MIN or y1 - y0 < LADO_MIN:
            raise HTTPException(422, "Caixa demasiado pequena")
    origem= next((i["origem"] for i in construir_fila(imagens) if i["id"] == id_fonte), "aleatoria")
    registo= {
        "id": id_fonte,
        "origem": origem,
        "camera_type": dados["camera_type"],
        "width": largura,
        "height": altura,
        "lat": dados["lat"],
        "lon": dados["lon"],
        "caixas": [c.model_dump() for c in pedido.caixas],
        "t": int(time.time()),
    }
    ficheiro= ficheiro_rotulos(lote)
    with trinco:
        ficheiro.parent.mkdir(parents=True, exist_ok=True)
        with ficheiro.open("a", encoding="utf-8") as saida:
            saida.write(json.dumps(registo, ensure_ascii=False) + "\n")
    return {"ok": True, "caixas": len(pedido.caixas)}
