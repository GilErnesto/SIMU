from datetime import datetime

from geoalchemy2 import Geography, Geometry, WKTElement
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    cast,
    func,
    select,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from pipeline.config import Classes
from pipeline.models import Element, ImageRecord

PESO_OBSERVACOES= 0.25


class Base(DeclarativeBase):
    pass


class Imagem(Base):
    __tablename__= "imagem"
    __table_args__= (UniqueConstraint("fonte", "id_fonte"),)

    id: Mapped[int]= mapped_column(primary_key=True)
    fonte: Mapped[str]= mapped_column(String(16))
    id_fonte: Mapped[str]= mapped_column(String(64))
    autor: Mapped[str]= mapped_column(String(128))
    licenca: Mapped[str]= mapped_column(String(32))
    url_origem: Mapped[str]= mapped_column(String(512))
    capturada_em: Mapped[datetime | None]= mapped_column(DateTime(timezone=True))
    geom= mapped_column(Geometry("POINT", srid=4326))
    heading: Mapped[float | None]= mapped_column(Float)
    camera_type: Mapped[str | None]= mapped_column(String(16))
    caminho_anon: Mapped[str | None]= mapped_column(String(512))


class Elemento(Base):
    __tablename__= "elemento"
    __table_args__= (
        CheckConstraint("estado IN ('auto', 'validado', 'corrigido', 'rejeitado')"),
    )

    id: Mapped[int]= mapped_column(primary_key=True)
    categoria: Mapped[str]= mapped_column(String(32))
    classe: Mapped[str]= mapped_column(String(32))
    geom= mapped_column(Geometry("POINT", srid=4326))
    confianca: Mapped[float]= mapped_column(Float)
    obstruido: Mapped[bool]= mapped_column(Boolean, default=False)
    estado: Mapped[str]= mapped_column(String(16), default="auto")
    metodo_geo: Mapped[str]= mapped_column(String(16))
    n_observacoes: Mapped[int]= mapped_column(Integer, default=0)
    criado_em: Mapped[datetime]= mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime]= mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    observacoes: Mapped[list["Observacao"]]= relationship(back_populates="elemento")


class Observacao(Base):
    __tablename__= "observacao"

    id: Mapped[int]= mapped_column(primary_key=True)
    elemento_id: Mapped[int]= mapped_column(ForeignKey("elemento.id"))
    imagem_id: Mapped[int]= mapped_column(ForeignKey("imagem.id"))
    bbox= mapped_column(JSON)
    classe: Mapped[str]= mapped_column(String(32))
    confianca: Mapped[float]= mapped_column(Float)
    bearing: Mapped[float]= mapped_column(Float)
    elemento: Mapped[Elemento]= relationship(back_populates="observacoes")
    imagem: Mapped[Imagem]= relationship()


class Correcao(Base):
    __tablename__= "correcao"

    id: Mapped[int]= mapped_column(primary_key=True)
    elemento_id: Mapped[int]= mapped_column(ForeignKey("elemento.id"))
    campo: Mapped[str]= mapped_column(String(32))
    valor_antigo: Mapped[str | None]= mapped_column(Text)
    valor_novo: Mapped[str | None]= mapped_column(Text)
    autor: Mapped[str]= mapped_column(String(128))
    em: Mapped[datetime]= mapped_column(DateTime(timezone=True), server_default=func.now())


def ensure_schema(engine: Engine) -> None:
    with engine.begin() as conexao:
        conexao.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(engine)


def element_confidence(media: float, n_observacoes: int) -> float:
    # confiança= média * (1 - 0.25 ** n)
    return media * (1 - PESO_OBSERVACOES**n_observacoes)


def known_image_ids(session: Session, fonte: str) -> set[str]:
    return set(session.scalars(select(Imagem.id_fonte).where(Imagem.fonte == fonte)))


def _ponto(lon: float, lat: float) -> WKTElement:
    return WKTElement(f"POINT({lon} {lat})", srid=4326)


def _vizinho(session: Session, elemento: Element, raio_m: float) -> Elemento | None:
    alvo= cast(_ponto(elemento.lon, elemento.lat), Geography)
    distancia= cast(Elemento.geom, Geography)
    consulta= (
        select(Elemento)
        .where(
            Elemento.classe == elemento.class_name,
            func.ST_DWithin(distancia, alvo, raio_m),
        )
        .order_by(func.ST_Distance(distancia, alvo))
        .limit(1)
    )
    return session.scalars(consulta).first()


def _refresh(session: Session, elemento: Elemento) -> None:
    n, media= session.execute(
        select(func.count(Observacao.id), func.avg(Observacao.confianca)).where(
            Observacao.elemento_id == elemento.id
        )
    ).one()
    elemento.n_observacoes= n
    elemento.confianca= element_confidence(float(media), n)


def write_catalog(
    session: Session, classes: Classes, images: list[ImageRecord], elements: list[Element]
) -> None:
    imagens= {}
    for registo in images:
        linha= Imagem(
            fonte=registo.fonte,
            id_fonte=registo.id_fonte,
            autor=registo.autor,
            licenca=registo.licenca,
            url_origem=registo.url_origem,
            capturada_em=registo.capturada_em,
            geom=_ponto(registo.lon, registo.lat),
            heading=registo.heading,
            camera_type=registo.camera_type,
            caminho_anon=registo.caminho_anon,
        )
        session.add(linha)
        imagens[registo.id]= linha
    session.flush()
    for elemento in elements:
        raio= classes.categorias[elemento.category].raio_dedup_m
        linha= _vizinho(session, elemento, raio)
        if linha is None:
            linha= Elemento(
                categoria=elemento.category,
                classe=elemento.class_name,
                geom=_ponto(elemento.lon, elemento.lat),
                confianca=0.0,
                obstruido=elemento.obstruido,
                metodo_geo=elemento.metodo_geo,
                n_observacoes=0,
            )
            session.add(linha)
            session.flush()
        else:
            linha.obstruido= linha.obstruido and elemento.obstruido
        for obs in elemento.observations:
            session.add(
                Observacao(
                    elemento_id=linha.id,
                    imagem_id=imagens[obs.image.id].id,
                    bbox=list(obs.detection.bbox_xyxy),
                    classe=obs.detection.class_name,
                    confianca=obs.detection.confidence,
                    bearing=obs.bearing,
                )
            )
        session.flush()
        _refresh(session, linha)
    session.flush()
