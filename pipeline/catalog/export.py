import csv
import io

from geoalchemy2.shape import to_shape
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from pipeline.catalog.reportes import abertos_por_elemento
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


def _carregar(
    session: Session,
    estado: str | None,
    categoria: str | None= None,
    bbox: tuple[float, float, float, float] | None= None,
    min_observacoes: int | None= None,
    min_confianca: float | None= None,
    analise_id: int | None= None,
    classe: str | None= None,
) -> list[Elemento]:
    consulta= select(Elemento).options(
        selectinload(Elemento.observacoes).selectinload(Observacao.imagem)
    )
    if estado is not None:
        consulta= consulta.where(Elemento.estado == estado)
    if categoria is not None:
        consulta= consulta.where(Elemento.categoria == categoria)
    if bbox is not None:
        consulta= consulta.where(
            func.ST_Intersects(Elemento.geom, func.ST_MakeEnvelope(*bbox, 4326))
        )
    if min_observacoes is not None:
        consulta= consulta.where(Elemento.n_observacoes >= min_observacoes)
    if min_confianca is not None:
        consulta= consulta.where(Elemento.confianca >= min_confianca)
    if analise_id is not None:
        consulta= consulta.where(Elemento.analise_id == analise_id)
    if classe is not None:
        consulta= consulta.where(Elemento.classe == classe)
    return list(session.scalars(consulta.order_by(Elemento.id)))


def to_feature(elemento: Elemento, reportes_abertos: int= 0) -> dict:
    """reportes_abertos: citizens' reports still open for it, the only source of "problem" on the map."""
    ponto= None if elemento.geom is None else to_shape(elemento.geom)
    return {
        "type": "Feature",
        "geometry": None if ponto is None else {"type": "Point", "coordinates": [ponto.x, ponto.y]},
        "properties": {
            "id": elemento.id,
            "categoria": elemento.categoria,
            "classe": elemento.classe,
            "confianca": elemento.confianca,
            "obstruido": elemento.obstruido,
            "estado": elemento.estado,
            "metodo_geo": elemento.metodo_geo,
            "n_observacoes": elemento.n_observacoes,
            "reportes_abertos": reportes_abertos,
            "atribuicao": _atribuicao(elemento),
        },
    }


def to_geojson(
    session: Session,
    estado: str | None= None,
    categoria: str | None= None,
    bbox: tuple[float, float, float, float] | None= None,
    min_observacoes: int | None= None,
    min_confianca: float | None= None,
    analise_id: int | None= None,
    classe: str | None= None,
    com_reportes: bool= False,
) -> dict:
    elementos= _carregar(session, estado, categoria, bbox, min_observacoes, min_confianca, analise_id, classe)
    abertos= abertos_por_elemento(session, [e.id for e in elementos])
    if com_reportes:
        elementos= [e for e in elementos if abertos.get(e.id)]
    return {
        "type": "FeatureCollection",
        "features": [to_feature(e, abertos.get(e.id, 0)) for e in elementos],
    }


def to_csv(
    session: Session,
    estado: str | None= None,
    categoria: str | None= None,
    min_observacoes: int | None= None,
    min_confianca: float | None= None,
    analise_id: int | None= None,
    classe: str | None= None,
) -> str:
    saida= io.StringIO()
    escritor= csv.DictWriter(saida, fieldnames=COLUNAS_CSV)
    escritor.writeheader()
    for elemento in _carregar(
        session, estado, categoria, None, min_observacoes, min_confianca, analise_id, classe
    ):
        feature= to_feature(elemento)
        propriedades= feature["properties"]
        lon, lat= feature["geometry"]["coordinates"] if feature["geometry"] else ("", "")
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
