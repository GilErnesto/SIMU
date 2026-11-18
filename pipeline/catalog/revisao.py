from collections import defaultdict

import numpy as np
from geoalchemy2 import WKTElement
from geoalchemy2.shape import to_shape
from pyproj import Transformer
from scipy.spatial import cKDTree
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from pipeline.catalog.write import Correcao, Elemento, Observacao, _refresh

RAIO_DUPLICADOS_M= 4.0


class ErroRevisao(Exception):
    def __init__(self, mensagem: str, codigo: int= 422):
        super().__init__(mensagem)
        self.codigo= codigo


def _carregar(sessao: Session, ids: list[int]) -> dict[int, Elemento]:
    linhas= sessao.scalars(select(Elemento).where(Elemento.id.in_(ids)).with_for_update()).all()
    encontrados= {linha.id: linha for linha in linhas}
    for identificador in ids:
        if identificador not in encontrados:
            raise ErroRevisao(f"Elemento {identificador} não encontrado", 404)
    return encontrados


def _registar(sessao: Session, elemento_id: int, autor: str, campo: str, antigo: str, novo: str) -> None:
    sessao.add(Correcao(elemento_id=elemento_id, campo=campo, valor_antigo=antigo, valor_novo=novo, autor=autor))


def _mover_observacoes(sessao: Session, de: Elemento, para: Elemento, ids: set[int] | None= None) -> None:
    consulta= update(Observacao).where(Observacao.elemento_id == de.id)
    if ids is not None:
        consulta= consulta.where(Observacao.id.in_(ids))
    sessao.execute(consulta.values(elemento_id=para.id))
    sessao.flush()
    sessao.expire(de, ["observacoes"])
    sessao.expire(para, ["observacoes"])


def juntar(sessao: Session, destino_id: int, origem_id: int, autor: str) -> Elemento:
    if destino_id == origem_id:
        raise ErroRevisao("Escolha dois elementos diferentes")
    elementos= _carregar(sessao, [destino_id, origem_id])
    destino, origem= elementos[destino_id], elementos[origem_id]
    if destino.analise_id != origem.analise_id:
        raise ErroRevisao("Os elementos são de análises diferentes")
    if destino.categoria != origem.categoria:
        raise ErroRevisao("Os elementos são de categorias diferentes")
    if "rejeitado" in (destino.estado, origem.estado):
        raise ErroRevisao("Não se juntam elementos rejeitados")
    ponto_destino= None if destino.geom is None else to_shape(destino.geom)
    ponto_origem= None if origem.geom is None else to_shape(origem.geom)
    anterior= "" if ponto_destino is None else f"{ponto_destino.x},{ponto_destino.y}"
    if ponto_destino is not None and ponto_origem is not None:
        n_destino, n_origem= max(destino.n_observacoes, 1), max(origem.n_observacoes, 1)
        total= n_destino + n_origem
        lon= (ponto_destino.x * n_destino + ponto_origem.x * n_origem) / total
        lat= (ponto_destino.y * n_destino + ponto_origem.y * n_origem) / total
        destino.geom= WKTElement(f"POINT({lon} {lat})", srid=4326)
        _registar(sessao, destino.id, autor, "posicao", anterior, f"{lon},{lat}")
    elif ponto_origem is not None:
        destino.geom= origem.geom
        destino.metodo_geo= origem.metodo_geo
        _registar(sessao, destino.id, autor, "posicao", anterior, f"{ponto_origem.x},{ponto_origem.y}")
    destino.obstruido= destino.obstruido and origem.obstruido
    _mover_observacoes(sessao, origem, destino)
    _refresh(sessao, destino)
    _registar(sessao, destino.id, autor, "juntar", "", f"elemento {origem.id}")
    if destino.estado == "auto":
        _registar(sessao, destino.id, autor, "estado", "auto", "corrigido")
        destino.estado= "corrigido"
    _registar(sessao, origem.id, autor, "juntado_em", "", str(destino.id))
    _registar(sessao, origem.id, autor, "estado", origem.estado, "rejeitado")
    origem.estado= "rejeitado"
    origem.n_observacoes= 0
    origem.confianca= 0.0
    sessao.flush()
    return destino


def separar(sessao: Session, elemento_id: int, observacoes_ids: list[int], autor: str) -> tuple[Elemento, Elemento]:
    elemento= _carregar(sessao, [elemento_id])[elemento_id]
    if elemento.estado == "rejeitado":
        raise ErroRevisao("Não se separa um elemento rejeitado")
    existentes= {obs.id for obs in elemento.observacoes}
    escolhidas= set(observacoes_ids)
    if not escolhidas:
        raise ErroRevisao("Escolha pelo menos uma fotografia para separar")
    if not escolhidas <= existentes:
        raise ErroRevisao("Há fotografias que não pertencem a este elemento")
    if escolhidas == existentes:
        raise ErroRevisao("Tem de ficar pelo menos uma fotografia no elemento original")
    novo= Elemento(
        categoria=elemento.categoria,
        classe=elemento.classe,
        geom=None,
        confianca=0.0,
        obstruido=elemento.obstruido,
        estado="corrigido",
        metodo_geo="sem_posicao",
        n_observacoes=0,
        analise_id=elemento.analise_id,
    )
    sessao.add(novo)
    sessao.flush()
    _mover_observacoes(sessao, elemento, novo, escolhidas)
    _refresh(sessao, elemento)
    _refresh(sessao, novo)
    _registar(sessao, elemento.id, autor, "separar", "", f"{len(escolhidas)} fotografias para o elemento {novo.id}")
    _registar(sessao, novo.id, autor, "separado_de", "", str(elemento.id))
    if elemento.estado == "auto":
        _registar(sessao, elemento.id, autor, "estado", "auto", "corrigido")
        elemento.estado= "corrigido"
    sessao.flush()
    return elemento, novo


def duplicados(sessao: Session, analise_id: int, crs_metrico: str, raio_m: float= RAIO_DUPLICADOS_M) -> list[dict]:
    linhas= sessao.execute(
        select(Elemento.id, Elemento.categoria, Elemento.classe, Elemento.geom).where(
            Elemento.analise_id == analise_id,
            Elemento.estado != "rejeitado",
            Elemento.geom.is_not(None),
        )
    ).all()
    if len(linhas) < 2:
        return []
    para_metros= Transformer.from_crs("EPSG:4326", crs_metrico, always_xy=True)
    imagens= defaultdict(set)
    for elemento_id, imagem_id in sessao.execute(
        select(Observacao.elemento_id, Observacao.imagem_id).where(Observacao.elemento_id.in_([linha[0] for linha in linhas]))
    ):
        imagens[elemento_id].add(imagem_id)
    por_categoria= defaultdict(list)
    for elemento_id, categoria, classe, geom in linhas:
        ponto= to_shape(geom)
        por_categoria[categoria].append((elemento_id, classe, para_metros.transform(ponto.x, ponto.y)))
    pares= []
    for categoria, itens in por_categoria.items():
        if len(itens) < 2:
            continue
        coordenadas= np.array([item[2] for item in itens])
        for i, j in cKDTree(coordenadas).query_pairs(raio_m):
            a, b= sorted((itens[i], itens[j]), key=lambda item: item[0])
            distancia= float(np.hypot(*(np.array(a[2]) - np.array(b[2]))))
            pares.append(
                {
                    "a": a[0],
                    "b": b[0],
                    "categoria": categoria,
                    "classe_a": a[1],
                    "classe_b": b[1],
                    "distancia_m": round(distancia, 1),
                    "fotos_em_comum": len(imagens[a[0]] & imagens[b[0]]),
                }
            )
    return sorted(pares, key=lambda par: (par["distancia_m"], par["a"], par["b"]))
