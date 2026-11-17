import os
import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from geoalchemy2 import WKTElement
from geoalchemy2.shape import to_shape
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.deps import anon_dir, get_classes, get_engine, get_municipio, get_session, raw_dir
from pipeline.catalog import analises
from pipeline.catalog.export import to_csv, to_feature, to_geojson
from pipeline.catalog.write import Analise, Correcao, Elemento, Imagem, Observacao, ensure_schema
from pipeline.config import Classes, Municipio
from pipeline.errors import ErroPipeline
from pipeline.ingest.uploads import tipo_de

load_dotenv()

Estado= Literal["auto", "validado", "corrigido", "rejeitado"]

@asynccontextmanager
async def ciclo_de_vida(_):
    ensure_schema(get_engine())
    yield


app= FastAPI(title="Ctrl + F", lifespan=ciclo_de_vida)


@app.exception_handler(ErroPipeline)
def erro_configuracao(_, erro: ErroPipeline):
    return JSONResponse(status_code=500, content={"detail": str(erro)})


class CorrecaoPedido(BaseModel):
    autor: str= Field(min_length=1, max_length=128)
    classe: str | None= None
    lon: float | None= Field(default=None, ge=-180, le=180)
    lat: float | None= Field(default=None, ge=-90, le=90)
    estado: Estado | None= None

    @model_validator(mode="after")
    def validar(self):
        if (self.lon is None) != (self.lat is None):
            raise ValueError("lon e lat têm de vir juntos")
        if self.classe is None and self.lon is None and self.estado is None:
            raise ValueError("Nada para corrigir: indique classe, posição ou estado")
        return self


def _bbox(valor: str | None) -> tuple[float, float, float, float] | None:
    if valor is None:
        return None
    try:
        lon_min, lat_min, lon_max, lat_max= (float(v) for v in valor.split(","))
    except ValueError:
        raise HTTPException(422, "bbox inválida: use lon_min,lat_min,lon_max,lat_max") from None
    if lon_min >= lon_max or lat_min >= lat_max:
        raise HTTPException(422, "bbox inválida: os mínimos têm de ser menores que os máximos")
    return lon_min, lat_min, lon_max, lat_max


def _verificar_categoria(categoria: str | None, classes: Classes) -> None:
    if categoria is not None and categoria not in classes.categorias:
        raise HTTPException(422, f"Categoria desconhecida: {categoria}")


def _elemento(sessao: Session, elemento_id: int) -> Elemento:
    consulta= (
        select(Elemento)
        .where(Elemento.id == elemento_id)
        .options(selectinload(Elemento.observacoes).selectinload(Observacao.imagem))
    )
    elemento= sessao.scalars(consulta).first()
    if elemento is None:
        raise HTTPException(404, "Elemento não encontrado")
    return elemento


def _detalhe(elemento: Elemento) -> dict:
    feature= to_feature(elemento)
    feature["properties"]["observacoes"]= [
        {
            "id": obs.id,
            "bbox": obs.bbox,
            "classe": obs.classe,
            "confianca": obs.confianca,
            "bearing": obs.bearing,
            "imagem": {
                "id": obs.imagem.id,
                "fonte": obs.imagem.fonte,
                "autor": obs.imagem.autor,
                "licenca": obs.imagem.licenca,
                "url_origem": obs.imagem.url_origem,
                "capturada_em": obs.imagem.capturada_em,
                "url": f"/imagens/{obs.imagem.id}" if obs.imagem.caminho_anon else None,
            },
        }
        for obs in elemento.observacoes
    ]
    return feature


def _analise_id(sessao: Session, token: str | None) -> int | None:
    if token is None:
        return None
    analise= analises.obter_por_token(sessao, token)
    if analise is None:
        raise HTTPException(404, "Análise não encontrada")
    return analise.id


@app.get("/config")
def configuracao(
    municipio: Municipio= Depends(get_municipio), classes: Classes= Depends(get_classes)
):
    return {
        "nome": municipio.nome,
        "bbox": municipio.bbox,
        "categorias": {
            nome: {
                "rotulo": cat.rotulo,
                "classes": [{"id": c, "rotulo": cat.rotulos.get(c, c)} for c in cat.classes],
            }
            for nome, cat in classes.categorias.items()
        },
        "estados": list(Estado.__args__),
    }


@app.get("/elementos")
def listar(
    bbox: str | None= None,
    categoria: str | None= None,
    estado: Estado | None= None,
    min_observacoes: int | None= Query(default=None, ge=1),
    min_confianca: float | None= Query(default=None, ge=0, le=1),
    analise: str | None= None,
    classe: str | None= None,
    sessao: Session= Depends(get_session),
    classes: Classes= Depends(get_classes),
):
    _verificar_categoria(categoria, classes)
    return to_geojson(
        sessao,
        estado,
        categoria,
        _bbox(bbox),
        min_observacoes=min_observacoes,
        min_confianca=min_confianca,
        analise_id=_analise_id(sessao, analise),
        classe=classe,
    )


@app.get("/elementos/{elemento_id}")
def obter(elemento_id: int, sessao: Session= Depends(get_session)):
    return _detalhe(_elemento(sessao, elemento_id))


@app.patch("/elementos/{elemento_id}")
def corrigir(
    elemento_id: int,
    pedido: CorrecaoPedido,
    sessao: Session= Depends(get_session),
    classes: Classes= Depends(get_classes),
):
    elemento= _elemento(sessao, elemento_id)
    if pedido.classe is not None and pedido.classe not in classes.categorias[elemento.categoria].classes:
        raise HTTPException(422, f"Classe inválida para a categoria {elemento.categoria}")
    alteracoes= []
    if pedido.classe is not None and pedido.classe != elemento.classe:
        alteracoes.append(("classe", elemento.classe, pedido.classe))
        elemento.classe= pedido.classe
    if pedido.lon is not None:
        antigo= to_shape(elemento.geom)
        if (antigo.x, antigo.y) != (pedido.lon, pedido.lat):
            alteracoes.append(("posicao", f"{antigo.x},{antigo.y}", f"{pedido.lon},{pedido.lat}"))
            elemento.geom= WKTElement(f"POINT({pedido.lon} {pedido.lat})", srid=4326)
    novo_estado= pedido.estado
    if novo_estado is None and alteracoes:
        novo_estado= "corrigido"
    if novo_estado is not None and novo_estado != elemento.estado:
        alteracoes.append(("estado", elemento.estado, novo_estado))
        elemento.estado= novo_estado
    for campo, antigo, novo in alteracoes:
        sessao.add(
            Correcao(
                elemento_id=elemento.id,
                campo=campo,
                valor_antigo=str(antigo),
                valor_novo=str(novo),
                autor=pedido.autor,
            )
        )
    sessao.commit()
    return _detalhe(_elemento(sessao, elemento_id))


@app.get("/imagens/{imagem_id}")
def imagem(imagem_id: int, sessao: Session= Depends(get_session)):
    registo= sessao.get(Imagem, imagem_id)
    if registo is None or not registo.caminho_anon:
        raise HTTPException(404, "Imagem não encontrada")
    ficheiro= anon_dir() / Path(registo.caminho_anon).name
    if not ficheiro.is_file():
        raise HTTPException(404, "Imagem não encontrada")
    return FileResponse(ficheiro, media_type="image/jpeg")


@app.get("/export.geojson")
def exportar_geojson(
    estado: Estado | None= None,
    categoria: str | None= None,
    min_observacoes: int | None= Query(default=None, ge=1),
    min_confianca: float | None= Query(default=None, ge=0, le=1),
    analise: str | None= None,
    classe: str | None= None,
    sessao: Session= Depends(get_session),
    classes: Classes= Depends(get_classes),
):
    _verificar_categoria(categoria, classes)
    return JSONResponse(
        to_geojson(
            sessao,
            estado,
            categoria,
            min_observacoes=min_observacoes,
            min_confianca=min_confianca,
            analise_id=_analise_id(sessao, analise),
            classe=classe,
        ),
        media_type="application/geo+json",
        headers={"Content-Disposition": 'attachment; filename="catalogo.geojson"'},
    )


@app.get("/export.csv")
def exportar_csv(
    estado: Estado | None= None,
    categoria: str | None= None,
    min_observacoes: int | None= Query(default=None, ge=1),
    min_confianca: float | None= Query(default=None, ge=0, le=1),
    analise: str | None= None,
    classe: str | None= None,
    sessao: Session= Depends(get_session),
    classes: Classes= Depends(get_classes),
):
    _verificar_categoria(categoria, classes)
    return Response(
        to_csv(
            sessao,
            estado,
            categoria,
            min_observacoes=min_observacoes,
            min_confianca=min_confianca,
            analise_id=_analise_id(sessao, analise),
            classe=classe,
        ),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="catalogo.csv"'},
    )


LIMITE_FICHEIROS= 2000
BLOCO= 1024 * 1024


def _limite_bytes() -> int:
    return int(os.environ.get("MAX_UPLOAD_MB", "8192")) * 1024 * 1024


def _formato_valido(tipo: str, cabecalho: bytes) -> bool:
    if tipo == "imagem":
        return cabecalho.startswith((b"\xff\xd8\xff", b"\x89PNG"))
    if tipo == "video":
        return cabecalho[4:8] == b"ftyp" or cabecalho.startswith((b"RIFF", b"\x1a\x45\xdf\xa3"))
    return cabecalho.lstrip().startswith(b"<?xml") or b"<gpx" in cabecalho[:4096].lower()


def _analise_json(analise: Analise) -> dict:
    return {
        "token": analise.token,
        "nome": analise.nome,
        "estado": analise.estado,
        "total": analise.total,
        "feitas": analise.feitas,
        "n_elementos": analise.n_elementos,
        "avisos": analise.avisos or [],
        "erro": analise.erro,
        "parametros": analise.parametros or {},
        "criada_em": analise.criada_em,
        "iniciada_em": analise.iniciada_em,
        "concluida_em": analise.concluida_em,
    }


@app.post("/analises", status_code=201)
async def criar_analise(
    ficheiros: list[UploadFile]= File(...),
    nome: str= Form(""),
    offset_s: float= Form(0.0),
    fps: float= Form(2.0),
    sessao: Session= Depends(get_session),
):
    if not ficheiros:
        raise HTTPException(400, "Não foi enviado nenhum ficheiro")
    if len(ficheiros) > LIMITE_FICHEIROS:
        raise HTTPException(400, f"Demasiados ficheiros de uma vez (máximo {LIMITE_FICHEIROS})")
    if not 0.2 <= fps <= 10:
        raise HTTPException(422, "As imagens por segundo do vídeo têm de estar entre 0,2 e 10")
    token= analises.novo_token()
    pasta= raw_dir() / token
    pasta.mkdir(parents=True, exist_ok=False)
    avisos= []
    guardados= {"imagem": 0, "video": 0, "gpx": 0}
    total= 0
    limite= _limite_bytes()
    try:
        for n, ficheiro in enumerate(ficheiros, 1):
            original= Path(ficheiro.filename or "sem_nome").name
            tipo= tipo_de(original)
            if tipo is None:
                avisos.append(f"{original}: tipo de ficheiro não suportado, ignorado")
                continue
            seguro= re.sub(r"[^A-Za-z0-9._-]+", "_", original)[-80:]
            destino= pasta / f"{n:04d}_{seguro}"
            primeiro= await ficheiro.read(BLOCO)
            if not _formato_valido(tipo, primeiro):
                avisos.append(f"{original}: o conteúdo não corresponde ao tipo de ficheiro, ignorado")
                continue
            bloco= primeiro
            with destino.open("wb") as saida:
                while bloco:
                    total+= len(bloco)
                    if total > limite:
                        raise HTTPException(413, "O envio ultrapassa o tamanho máximo permitido")
                    saida.write(bloco)
                    bloco= await ficheiro.read(BLOCO)
            guardados[tipo]+= 1
        if guardados["imagem"] + guardados["video"] == 0:
            raise HTTPException(400, "Nenhuma imagem ou vídeo válido. Aceita JPG, PNG e vídeos MP4, MOV, AVI ou WEBM.")
    except BaseException:
        shutil.rmtree(pasta, ignore_errors=True)
        raise
    if guardados["video"] and not guardados["gpx"]:
        avisos.append("Enviou vídeo sem ficheiro GPX: sem ele não é possível localizar os elementos do vídeo")
    analise= analises.criar(
        sessao,
        nome.strip()[:120] or "Análise sem nome",
        {"offset_s": offset_s, "fps": fps},
        avisos,
        token=token,
    )
    return {"token": analise.token, "url": f"/a/{analise.token}", "estado": analise.estado}


@app.get("/analises")
def listar_analises(sessao: Session= Depends(get_session)):
    linhas= sessao.scalars(select(Analise).order_by(Analise.id.desc()).limit(100))
    return [_analise_json(a) for a in linhas]


@app.get("/analises/{token}")
def obter_analise(token: str, sessao: Session= Depends(get_session)):
    analise= analises.obter_por_token(sessao, token)
    if analise is None:
        raise HTTPException(404, "Análise não encontrada")
    return _analise_json(analise)
