"""Problems reported by citizens: photo -> detected objects -> the citizen picks one and the problem ->
technician queue -> resolved -> the citizen is notified. Every change is logged in reporte_evento."""

import secrets
from datetime import UTC, datetime
from pathlib import Path

import cv2
from geoalchemy2 import Geography, WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from pipeline.catalog.write import Elemento, Notificacao, Reporte, ReporteEvento
from pipeline.config import Classes

# Report states: rascunho (photo sent, object not chosen yet) -> aberto -> em_resolucao -> resolvido | rejeitado.
ESTADOS_TECNICO= ("aberto", "em_resolucao", "resolvido", "rejeitado")
ABERTOS= ("aberto", "em_resolucao")
RAIO_ELEMENTO_M= 15.0
LADO_MAXIMO= 2048
AUTOR_CIDADAO= "cidadão"
AVISOS= {
    "em_resolucao": "está a ser tratado pela Câmara",
    "resolvido": "foi resolvido. Obrigado por ajudar",
    "rejeitado": "foi analisado e não precisa de intervenção",
    "aberto": "foi reaberto",
}


class ErroReporte(Exception):
    def __init__(self, mensagem: str, codigo: int= 422):
        super().__init__(mensagem)
        self.codigo= codigo


def _ponto(lon: float | None, lat: float | None) -> WKTElement | None:
    if lon is None or lat is None:
        return None
    return WKTElement(f"POINT({lon} {lat})", srid=4326)


def _evento(sessao: Session, reporte: Reporte, estado: str, autor: str, nota: str | None= None) -> None:
    sessao.add(ReporteEvento(reporte_id=reporte.id, estado=estado, autor=autor, nota=nota))


def caminho_raw(pasta_raw: Path, token: str) -> Path:
    return pasta_raw / "reportes" / f"{token}.jpg"


def caminho_foto(pasta_anon: Path, token: str) -> Path:
    return pasta_anon / f"reporte_{token}.jpg"


def novo_token() -> str:
    return secrets.token_urlsafe(8)


def criar(
    sessao: Session, cidadao_id: str, lon: float | None= None, lat: float | None= None, token: str | None= None
) -> Reporte:
    """token: given when the photo was already saved under it (the worker must never see a report without one)."""
    reporte= Reporte(
        token=token or novo_token(),
        cidadao_id=cidadao_id,
        estado="rascunho",
        estado_foto="na_fila",
        caixas=[],
        geom=_ponto(lon, lat),
        origem_posicao=None if lon is None else "browser",
    )
    sessao.add(reporte)
    sessao.flush()
    _evento(sessao, reporte, "rascunho", AUTOR_CIDADAO, "Fotografia enviada")
    sessao.commit()
    return reporte


def obter(sessao: Session, token: str) -> Reporte:
    reporte= sessao.scalar(select(Reporte).where(Reporte.token == token))
    if reporte is None:
        raise ErroReporte("Reporte não encontrado", 404)
    return reporte


def reclamar_foto(sessao: Session) -> Reporte | None:
    consulta= (
        select(Reporte)
        .where(Reporte.estado_foto == "na_fila")
        .order_by(Reporte.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    reporte= sessao.scalars(consulta).first()
    if reporte is None:
        sessao.rollback()
    return reporte


def processar_foto(sessao: Session, reporte: Reporte, anonimizador, detetor, pasta_raw: Path, pasta_anon: Path) -> bool:
    """Worker side: anonymise the photo, find the objects in it, delete the original."""
    original= caminho_raw(pasta_raw, reporte.token)
    try:
        imagem= cv2.imread(str(original))
        if imagem is None:
            raise ValueError("Não foi possível ler a fotografia")
        if reporte.geom is None:
            from pipeline.ingest.uploads import ler_exif

            exif= ler_exif(original)
            if exif["lat"] is not None:
                reporte.geom= _ponto(exif["lon"], exif["lat"])
                reporte.origem_posicao= "exif"
        maior= max(imagem.shape[:2])
        if maior > LADO_MAXIMO:
            escala= LADO_MAXIMO / maior
            imagem= cv2.resize(imagem, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
        anonima= anonimizador(imagem)
        destino= caminho_foto(pasta_anon, reporte.token)
        destino.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(destino), anonima):
            raise OSError(f"Não foi possível gravar {destino}")
        deteccoes= detetor.detect(f"reporte:{reporte.token}", anonima)
        reporte.caixas= [
            {
                "categoria": d.category,
                "classe": d.class_name,
                "caixa": [round(float(v), 1) for v in d.bbox_xyxy],
                "confianca": round(float(d.confidence), 3),
            }
            for d in sorted(deteccoes, key=lambda d: -d.confidence)
        ]
        reporte.caminho_anon= str(destino)
        reporte.altura, reporte.largura= anonima.shape[:2]
        reporte.estado_foto= "pronta"
        original.unlink(missing_ok=True)
    except Exception as erro:  # noqa: BLE001 - any failure is shown to the citizen, the worker goes on
        reporte.estado_foto= "falhou"
        reporte.erro= str(erro)[:500]
    sessao.commit()
    return reporte.estado_foto == "pronta"


def elemento_proximo(
    sessao: Session, categoria: str, lon: float, lat: float, classe: str | None= None, raio_m: float= RAIO_ELEMENTO_M
) -> Elemento | None:
    """Closest catalogue element of that category within raio_m; one of the same type wins over a closer one."""
    alvo= cast(_ponto(lon, lat), Geography)
    distancia= cast(Elemento.geom, Geography)
    consulta= (
        select(Elemento)
        .where(
            Elemento.categoria == categoria,
            Elemento.estado != "rejeitado",
            Elemento.geom.is_not(None),
            func.ST_DWithin(distancia, alvo, raio_m),
        )
        .order_by((Elemento.classe != classe) if classe else Elemento.id.is_(None), func.ST_Distance(distancia, alvo))
        .limit(1)
    )
    return sessao.scalars(consulta).first()


def validar_escolha(
    classes: Classes,
    reporte: Reporte,
    problema: str,
    indice: int | None,
    caixa: list[float] | None,
    categoria: str | None,
) -> tuple[str, str | None, list[float] | None]:
    """(categoria, classe, caixa) of the object the citizen picked: a detected box, or one they marked."""
    if reporte.estado != "rascunho":
        raise ErroReporte("Este reporte já foi enviado", 409)
    if indice is not None:
        if reporte.estado_foto != "pronta" or not 0 <= indice < len(reporte.caixas or []):
            raise ErroReporte("Escolha um dos objetos encontrados na fotografia")
        escolhida= reporte.caixas[indice]
        categoria, classe, caixa= escolhida["categoria"], escolhida["classe"], escolhida["caixa"]
    else:
        if categoria not in classes.categorias:
            raise ErroReporte("Indique se é um sinal, iluminação ou contentor")
        classe= None
    if problema not in classes.categorias[categoria].problemas:
        raise ErroReporte("Problema inválido para este tipo de objeto")
    return categoria, classe, caixa


def enviar(
    sessao: Session,
    classes: Classes,
    reporte: Reporte,
    problema: str,
    indice: int | None= None,
    caixa: list[float] | None= None,
    categoria: str | None= None,
    descricao: str | None= None,
    lon: float | None= None,
    lat: float | None= None,
) -> Reporte:
    categoria, classe, caixa= validar_escolha(classes, reporte, problema, indice, caixa, categoria)
    reporte.categoria, reporte.classe, reporte.caixa= categoria, classe, caixa
    reporte.problema= problema
    reporte.descricao= (descricao or "").strip()[:1000] or None
    if lon is not None and lat is not None:
        reporte.geom= _ponto(lon, lat)
        reporte.origem_posicao= "mapa"
    if reporte.geom is not None:
        ponto= to_shape(reporte.geom)
        elemento= elemento_proximo(sessao, categoria, ponto.x, ponto.y, classe)
        reporte.elemento_id= None if elemento is None else elemento.id
    reporte.estado= "aberto"
    _evento(sessao, reporte, "aberto", AUTOR_CIDADAO, classes.categorias[categoria].problemas[problema])
    sessao.commit()
    return reporte


def descrever(classes: Classes, reporte: Reporte) -> str:
    """'Sinal torto ou caído (Cedência de passagem)' style label."""
    categoria= classes.categorias.get(reporte.categoria or "")
    if categoria is None:
        return "Reporte"
    problema= categoria.problemas.get(reporte.problema or "", reporte.problema or "")
    tipo= categoria.rotulos.get(reporte.classe or "", "") if reporte.classe else categoria.rotulo
    return f"{problema} ({tipo})" if tipo else problema


def mudar_estado(sessao: Session, classes: Classes, reporte: Reporte, estado: str, autor: str, nota: str | None= None) -> Reporte:
    if estado not in ESTADOS_TECNICO:
        raise ErroReporte("Estado inválido")
    if reporte.estado == "rascunho":
        raise ErroReporte("O cidadão ainda não enviou este reporte", 409)
    if estado == reporte.estado:
        return reporte
    reporte.estado= estado
    reporte.atualizado_em= datetime.now(UTC)
    nota= (nota or "").strip()[:1000] or None
    _evento(sessao, reporte, estado, autor, nota)
    texto= f"O seu reporte “{descrever(classes, reporte)}” {AVISOS[estado]}."
    if nota:
        texto+= f" Nota do técnico: {nota}"
    sessao.add(Notificacao(cidadao_id=reporte.cidadao_id, reporte_id=reporte.id, texto=texto))
    sessao.commit()
    return reporte


def para_json(classes: Classes, reporte: Reporte, eventos: bool= False) -> dict:
    ponto= None if reporte.geom is None else to_shape(reporte.geom)
    dados= {
        "id": reporte.id,
        "token": reporte.token,
        "estado": reporte.estado,
        "estado_foto": reporte.estado_foto,
        "erro": reporte.erro,
        "foto": f"/reportes/{reporte.token}/foto" if reporte.caminho_anon else None,
        "largura": reporte.largura,
        "altura": reporte.altura,
        "caixas": reporte.caixas or [],
        "caixa": reporte.caixa,
        "categoria": reporte.categoria,
        "classe": reporte.classe,
        "problema": reporte.problema,
        "descricao": reporte.descricao,
        "titulo": descrever(classes, reporte),
        "lon": None if ponto is None else ponto.x,
        "lat": None if ponto is None else ponto.y,
        "origem_posicao": reporte.origem_posicao,
        "elemento_id": reporte.elemento_id,
        "criado_em": reporte.criado_em,
        "atualizado_em": reporte.atualizado_em,
    }
    if eventos:
        dados["eventos"]= [
            {"estado": e.estado, "autor": e.autor, "nota": e.nota, "em": e.em} for e in reporte.eventos
        ]
    return dados


def listar(sessao: Session, estados: tuple[str, ...] | None= None, categoria: str | None= None) -> list[Reporte]:
    consulta= select(Reporte).where(Reporte.estado != "rascunho")
    if estados:
        consulta= consulta.where(Reporte.estado.in_(estados))
    if categoria:
        consulta= consulta.where(Reporte.categoria == categoria)
    return list(sessao.scalars(consulta.order_by(Reporte.criado_em.desc())))


def abertos_por_elemento(sessao: Session, ids: list[int]) -> dict[int, int]:
    if not ids:
        return {}
    consulta= (
        select(Reporte.elemento_id, func.count(Reporte.id))
        .where(Reporte.elemento_id.in_(ids), Reporte.estado.in_(ABERTOS))
        .group_by(Reporte.elemento_id)
    )
    return dict(sessao.execute(consulta).all())
