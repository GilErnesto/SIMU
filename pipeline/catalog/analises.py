import secrets
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from pipeline.catalog.write import Analise, Correcao, Elemento, Imagem, Observacao


def novo_token() -> str:
    return secrets.token_urlsafe(6)


def criar(
    sessao: Session,
    nome: str,
    parametros: dict | None= None,
    avisos: list[str] | None= None,
    estado: str= "na_fila",
    token: str | None= None,
) -> Analise:
    analise= Analise(
        token=token or novo_token(),
        nome=nome,
        estado=estado,
        avisos=avisos or [],
        parametros=parametros or {},
    )
    sessao.add(analise)
    sessao.commit()
    return analise


def obter_por_token(sessao: Session, token: str) -> Analise | None:
    return sessao.scalar(select(Analise).where(Analise.token == token))


def criar_ou_obter(sessao: Session, token: str, nome: str) -> Analise:
    existente= obter_por_token(sessao, token)
    if existente is not None:
        return existente
    return criar(sessao, nome, estado="concluida", token=token)


def reclamar_proxima(sessao: Session) -> Analise | None:
    consulta= (
        select(Analise)
        .where(Analise.estado == "na_fila")
        .order_by(Analise.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    analise= sessao.scalars(consulta).first()
    if analise is None:
        sessao.rollback()
        return None
    analise.estado= "a_processar"
    analise.iniciada_em= datetime.now(UTC)
    analise.feitas= 0
    sessao.commit()
    return analise


def recuperar_interrompidas(sessao: Session) -> int:
    resultado= sessao.execute(
        update(Analise).where(Analise.estado == "a_processar").values(estado="na_fila")
    )
    sessao.commit()
    return resultado.rowcount


def registar_progresso(sessao: Session, analise: Analise, feitas: int, total: int) -> None:
    analise.feitas= feitas
    analise.total= total
    sessao.commit()


def concluir(sessao: Session, analise: Analise, n_elementos: int, avisos: list[str]) -> None:
    analise.estado= "concluida"
    analise.n_elementos= n_elementos
    analise.avisos= avisos
    analise.concluida_em= datetime.now(UTC)
    sessao.commit()


def falhar(sessao: Session, analise: Analise, erro: str, avisos: list[str] | None= None) -> None:
    sessao.rollback()
    analise.estado= "falhou"
    analise.erro= erro[:500]
    if avisos is not None:
        analise.avisos= avisos
    analise.concluida_em= datetime.now(UTC)
    sessao.commit()


def atualizar_contagens(sessao: Session, analise: Analise) -> None:
    analise.total= sessao.scalar(select(func.count(Imagem.id)).where(Imagem.analise_id == analise.id)) or 0
    analise.feitas= analise.total
    analise.n_elementos= (
        sessao.scalar(select(func.count(Elemento.id)).where(Elemento.analise_id == analise.id)) or 0
    )
    sessao.commit()


def apagar(sessao: Session, analise: Analise) -> tuple[int, int, list[str]]:
    ids_elementos= select(Elemento.id).where(Elemento.analise_id == analise.id)
    ficheiros= [
        caminho
        for caminho in sessao.scalars(select(Imagem.caminho_anon).where(Imagem.analise_id == analise.id))
        if caminho
    ]
    sessao.execute(delete(Correcao).where(Correcao.elemento_id.in_(ids_elementos)))
    sessao.execute(delete(Observacao).where(Observacao.elemento_id.in_(ids_elementos)))
    elementos= sessao.execute(delete(Elemento).where(Elemento.analise_id == analise.id)).rowcount
    imagens= sessao.execute(delete(Imagem).where(Imagem.analise_id == analise.id)).rowcount
    sessao.execute(delete(Analise).where(Analise.id == analise.id))
    sessao.commit()
    return elementos, imagens, ficheiros
