import csv
import io

from geoalchemy2.shape import to_shape
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from pipeline.catalog.write import Elemento, Observacao

COLUNAS_CSV= (
    "id",
    "categoria",
    "classe",
    "lon",
    "lat",
    "confianca",
    "obstruido",
    "estado",
    "metodo_geo",
    "n_observacoes",
    "autores",
    "urls_origem",
)


def _atribuicao(elemento: Elemento) -> list[dict]:
    vistos= {}
    for obs in elemento.observacoes:
        imagem= obs.imagem
        vistos[imagem.url_origem]= {
            "autor": imagem.autor,
            "fonte": imagem.fonte,
            "licenca": imagem.licenca,
            "url_origem": imagem.url_origem,
        }
    return list(vistos.values())


def _carregar(session: Session, estado: str | None) -> list[Elemento]:
    consulta= select(Elemento).options(
        selectinload(Elemento.observacoes).selectinload(Observacao.imagem)
    )
    if estado is not None:
        consulta= consulta.where(Elemento.estado == estado)
    return list(session.scalars(consulta.order_by(Elemento.id)))


def to_feature(elemento: Elemento) -> dict:
    ponto= to_shape(elemento.geom)
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [ponto.x, ponto.y]},
        "properties": {
            "id": elemento.id,
            "categoria": elemento.categoria,
            "classe": elemento.classe,
            "confianca": elemento.confianca,
            "obstruido": elemento.obstruido,
            "estado": elemento.estado,
            "metodo_geo": elemento.metodo_geo,
            "n_observacoes": elemento.n_observacoes,
            "atribuicao": _atribuicao(elemento),
        },
    }


def to_geojson(session: Session, estado: str | None= None) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [to_feature(e) for e in _carregar(session, estado)],
    }


def to_csv(session: Session, estado: str | None= None) -> str:
    saida= io.StringIO()
    escritor= csv.DictWriter(saida, fieldnames=COLUNAS_CSV)
    escritor.writeheader()
    for elemento in _carregar(session, estado):
        feature= to_feature(elemento)
        propriedades= feature["properties"]
        lon, lat= feature["geometry"]["coordinates"]
        atribuicao= propriedades["atribuicao"]
        escritor.writerow(
            {
                **{k: propriedades[k] for k in COLUNAS_CSV if k in propriedades},
                "lon": lon,
                "lat": lat,
                "autores": " | ".join(sorted({a["autor"] for a in atribuicao})),
                "urls_origem": " | ".join(a["url_origem"] for a in atribuicao),
            }
        )
    return saida.getvalue()
