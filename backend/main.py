from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse, JSONResponse
from geoalchemy2 import WKTElement
from geoalchemy2.shape import to_shape
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.deps import anon_dir, get_classes, get_municipio, get_session
from pipeline.catalog.export import to_csv, to_feature, to_geojson
from pipeline.catalog.write import Correcao, Elemento, Imagem, Observacao
from pipeline.config import Classes, Municipio
from pipeline.errors import ErroPipeline

load_dotenv()

Estado= Literal["auto", "validado", "corrigido", "rejeitado"]

app= FastAPI(title="Ctrl + F")


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
        ),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="catalogo.csv"'},
    )
