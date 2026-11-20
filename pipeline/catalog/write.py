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
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from pipeline.config import Classes, calibrar_confianca
from pipeline.models import Element, ImageRecord

PESO_OBSERVACOES= 0.25


class Base(DeclarativeBase):
    pass


class Analise(Base):
    __tablename__= "analise"

    id: Mapped[int]= mapped_column(primary_key=True)
    token: Mapped[str]= mapped_column(String(32), unique=True)
    nome: Mapped[str]= mapped_column(String(128))
    estado: Mapped[str]= mapped_column(String(16), default="na_fila")
    total: Mapped[int]= mapped_column(Integer, default=0)
    feitas: Mapped[int]= mapped_column(Integer, default=0)
    n_elementos: Mapped[int]= mapped_column(Integer, default=0)
    avisos= mapped_column(JSON, default=list)
    erro: Mapped[str | None]= mapped_column(Text)
    parametros= mapped_column(JSON, default=dict)
    criada_em: Mapped[datetime]= mapped_column(DateTime(timezone=True), server_default=func.now())
    iniciada_em: Mapped[datetime | None]= mapped_column(DateTime(timezone=True))
    concluida_em: Mapped[datetime | None]= mapped_column(DateTime(timezone=True))


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
    analise_id: Mapped[int | None]= mapped_column(ForeignKey("analise.id"), index=True)


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
    analise_id: Mapped[int | None]= mapped_column(ForeignKey("analise.id"), index=True)
    observacoes: Mapped[list["Observacao"]]= relationship(back_populates="elemento")


class Observacao(Base):
    __tablename__= "observacao"

    id: Mapped[int]= mapped_column(primary_key=True)
    elemento_id: Mapped[int]= mapped_column(ForeignKey("elemento.id"))
    imagem_id: Mapped[int]= mapped_column(ForeignKey("imagem.id"))
    bbox= mapped_column(JSON)
    classe: Mapped[str]= mapped_column(String(32))
    confianca: Mapped[float]= mapped_column(Float)
    bearing: Mapped[float | None]= mapped_column(Float)
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


class Reporte(Base):
    """A problem reported by a citizen from a photo (pipeline/catalog/reportes.py)."""

    __tablename__= "reporte"
    __table_args__= (
        CheckConstraint("estado IN ('rascunho', 'aberto', 'em_resolucao', 'resolvido', 'rejeitado')"),
        CheckConstraint("estado_foto IN ('na_fila', 'pronta', 'falhou')"),
    )

    id: Mapped[int]= mapped_column(primary_key=True)
    token: Mapped[str]= mapped_column(String(32), unique=True)
    cidadao_id: Mapped[str]= mapped_column(String(64), index=True)
    estado: Mapped[str]= mapped_column(String(16), default="rascunho")
    estado_foto: Mapped[str]= mapped_column(String(16), default="na_fila")
    erro: Mapped[str | None]= mapped_column(Text)
    caminho_anon: Mapped[str | None]= mapped_column(String(512))
    largura: Mapped[int]= mapped_column(Integer, default=0)
    altura: Mapped[int]= mapped_column(Integer, default=0)
    # Detector boxes on the photo: [{categoria, classe, caixa, confianca}], for the citizen to pick one.
    caixas= mapped_column(JSON, default=list)
    caixa: Mapped[list | None]= mapped_column(JSON)
    categoria: Mapped[str | None]= mapped_column(String(32))
    classe: Mapped[str | None]= mapped_column(String(32))
    problema: Mapped[str | None]= mapped_column(String(32))
    descricao: Mapped[str | None]= mapped_column(Text)
    geom= mapped_column(Geometry("POINT", srid=4326))
    origem_posicao: Mapped[str | None]= mapped_column(String(16))
    elemento_id: Mapped[int | None]= mapped_column(ForeignKey("elemento.id"), index=True)
    criado_em: Mapped[datetime]= mapped_column(DateTime(timezone=True), server_default=func.now())
    atualizado_em: Mapped[datetime]= mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    eventos: Mapped[list["ReporteEvento"]]= relationship(order_by="ReporteEvento.id")


class ReporteEvento(Base):
    """Every change of a report, never deleted: the report's log and archive."""

    __tablename__= "reporte_evento"

    id: Mapped[int]= mapped_column(primary_key=True)
    reporte_id: Mapped[int]= mapped_column(ForeignKey("reporte.id"), index=True)
    estado: Mapped[str]= mapped_column(String(16))
    autor: Mapped[str]= mapped_column(String(128))
    nota: Mapped[str | None]= mapped_column(Text)
    em: Mapped[datetime]= mapped_column(DateTime(timezone=True), server_default=func.now())


class Notificacao(Base):
    __tablename__= "notificacao"

    id: Mapped[int]= mapped_column(primary_key=True)
    cidadao_id: Mapped[str]= mapped_column(String(64), index=True)
    reporte_id: Mapped[int]= mapped_column(ForeignKey("reporte.id"))
    texto: Mapped[str]= mapped_column(Text)
    lida: Mapped[bool]= mapped_column(Boolean, default=False)
    criada_em: Mapped[datetime]= mapped_column(DateTime(timezone=True), server_default=func.now())


def ensure_schema(engine: Engine) -> None:
    with engine.begin() as conexao:
        conexao.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(engine)
    with engine.begin() as conexao:
        for tabela in ("imagem", "elemento"):
            conexao.execute(
                text(f"ALTER TABLE {tabela} ADD COLUMN IF NOT EXISTS analise_id integer REFERENCES analise(id)")
            )
            conexao.execute(
                text(f"CREATE INDEX IF NOT EXISTS ix_{tabela}_analise_id ON {tabela} (analise_id)")
            )
        conexao.execute(text("ALTER TABLE observacao ALTER COLUMN bearing DROP NOT NULL"))
    with Session(engine) as sessao:
        atribuir_analise_inicial(sessao)
        sessao.commit()


def atribuir_analise_inicial(sessao: Session) -> None:
    imagens= sessao.scalar(select(func.count(Imagem.id)).where(Imagem.analise_id.is_(None)))
    elementos= sessao.scalar(select(func.count(Elemento.id)).where(Elemento.analise_id.is_(None)))
    if not imagens and not elementos:
        return
    analise= sessao.scalar(select(Analise).where(Analise.token == "inicial"))
    if analise is None:
        analise= Analise(
            token="inicial", nome="Catálogo anterior", estado="concluida", avisos=[], parametros={}
        )
        sessao.add(analise)
        sessao.flush()
    sessao.execute(update(Imagem).where(Imagem.analise_id.is_(None)).values(analise_id=analise.id))
    sessao.execute(update(Elemento).where(Elemento.analise_id.is_(None)).values(analise_id=analise.id))
    analise.total= sessao.scalar(select(func.count(Imagem.id)).where(Imagem.analise_id == analise.id))
    analise.feitas= analise.total
    analise.n_elementos= sessao.scalar(
        select(func.count(Elemento.id)).where(Elemento.analise_id == analise.id)
    )
    sessao.flush()


def element_confidence(media: float, n_observacoes: int) -> float:
    # confiança= média * (1 - 0.25 ** n)
    return media * (1 - PESO_OBSERVACOES**n_observacoes)


def known_image_ids(session: Session, fonte: str) -> set[str]:
    return set(session.scalars(select(Imagem.id_fonte).where(Imagem.fonte == fonte)))


def anon_paths(session: Session, fonte: str) -> dict[str, str]:
    consulta= select(Imagem.id_fonte, Imagem.caminho_anon).where(
        Imagem.fonte == fonte, Imagem.caminho_anon.is_not(None)
    )
    return {id_fonte: caminho for id_fonte, caminho in session.execute(consulta)}


def _ponto(lon: float | None, lat: float | None) -> WKTElement | None:
    if lon is None or lat is None:
        return None
    return WKTElement(f"POINT({lon} {lat})", srid=4326)


def _vizinho(
    session: Session,
    elemento: Element,
    raio_m: float,
    analise_id: int | None= None,
    excluir: set[int] | None= None,
) -> Elemento | None:
    alvo= cast(_ponto(elemento.lon, elemento.lat), Geography)
    distancia= cast(Elemento.geom, Geography)
    consulta= (
        select(Elemento)
        .where(
            Elemento.classe == elemento.class_name,
            Elemento.analise_id.is_(None) if analise_id is None else Elemento.analise_id == analise_id,
            Elemento.id.not_in(excluir or set()),
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
    session: Session,
    classes: Classes,
    images: list[ImageRecord],
    elements: list[Element],
    analise_id: int | None= None,
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
            analise_id=analise_id,
        )
        session.add(linha)
        imagens[registo.id]= linha
    session.flush()
    criados= set()
    for elemento in elements:
        raio= classes.categorias[elemento.category].raio_dedup_m
        linha= _vizinho(session, elemento, raio, analise_id, criados) if elemento.lon is not None else None
        if linha is None:
            linha= Elemento(
                categoria=elemento.category,
                classe=elemento.class_name,
                geom=_ponto(elemento.lon, elemento.lat),
                confianca=0.0,
                obstruido=elemento.obstruido,
                metodo_geo=elemento.metodo_geo,
                n_observacoes=0,
                analise_id=analise_id,
            )
            session.add(linha)
            session.flush()
            criados.add(linha.id)
        else:
            linha.obstruido= linha.obstruido and elemento.obstruido
        for obs in elemento.observations:
            session.add(
                Observacao(
                    elemento_id=linha.id,
                    imagem_id=imagens[obs.image.id].id,
                    bbox=list(obs.detection.bbox_xyxy),
                    classe=obs.detection.class_name,
                    confianca=calibrar_confianca(
                        classes.categorias[elemento.category], obs.detection.confidence
                    ),
                    bearing=obs.bearing,
                )
            )
        session.flush()
        _refresh(session, linha)
    session.flush()
