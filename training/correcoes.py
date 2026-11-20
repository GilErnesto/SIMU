import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
from dotenv import load_dotenv
from geoalchemy2.shape import to_shape
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from pipeline.catalog.write import Base, Correcao, Elemento, Observacao
from pipeline.config import load_classes
from pipeline.detect.panorama import LADO_VISTA, views
from pipeline.errors import ErroPipeline
from training.rotulos_para_yolo import caixa_na_vista
from training.tipos import QUALIDADE_JPEG, divisao_de, recortes_de

NEGATIVOS= {"iluminacao": "nao_luz"}
REVISTOS= ("validado", "corrigido", "rejeitado")


def etiqueta(estado: str, classe: str, classe_corrigida: bool, categoria: str, gerais: set[str]) -> str | None:
    if estado == "rejeitado":
        return NEGATIVOS.get(categoria)
    if (estado == "validado" or classe_corrigida) and classe not in gerais:
        return classe
    return None


def posicao_do_tecnico(campos: set[str], estado: str) -> bool:
    return estado != "rejeitado" and "posicao" in campos and "juntar" not in campos


def _elementos(sessao: Session, tokens: list[str]) -> list[Elemento]:
    consulta= (
        select(Elemento)
        .options(selectinload(Elemento.observacoes).selectinload(Observacao.imagem))
        .where(Elemento.estado.in_(REVISTOS))
    )
    if tokens:
        tabela= Base.metadata.tables["analise"]
        consulta= consulta.where(Elemento.analise_id.in_(select(tabela.c.id).where(tabela.c.token.in_(tokens))))
    return list(sessao.scalars(consulta).all())


def _campos(sessao: Session) -> dict[int, set[str]]:
    campos= defaultdict(set)
    for elemento_id, campo in sessao.execute(select(Correcao.elemento_id, Correcao.campo)):
        campos[elemento_id].add(campo)
    return campos


def _recorte_do_panorama(vistas: list, bbox: list[float], largura: int, altura: int, classe: str):
    melhor= None
    for yaw, vista in vistas:
        mapeada= caixa_na_vista(tuple(bbox), yaw, largura, altura, LADO_VISTA)
        if mapeada is None:
            continue
        area= (mapeada[2] - mapeada[0]) * (mapeada[3] - mapeada[1])
        if melhor is None or area > melhor[0]:
            melhor= (area, vista, mapeada)
    if melhor is None:
        return None
    _, vista, (a, b, c, d)= melhor
    itens= [{"caixa": [a / LADO_VISTA, b / LADO_VISTA, c / LADO_VISTA, d / LADO_VISTA], "classe": classe}]
    recortes= recortes_de(vista, itens)
    return recortes[0][2] if recortes else None


def exportar_recortes(
    elementos: list[Elemento],
    campos: dict[int, set[str]],
    categoria: str,
    gerais: set[str],
    anon_dir: Path,
    saida: Path,
) -> tuple[Counter, Counter]:
    por_imagem= defaultdict(list)
    for elemento in elementos:
        if elemento.categoria != categoria:
            continue
        classe= etiqueta(elemento.estado, elemento.classe, "classe" in campos.get(elemento.id, ()), categoria, gerais)
        if classe is not None:
            for obs in elemento.observacoes:
                por_imagem[obs.imagem].append((obs, classe))
    contagem= Counter()
    ignorados= Counter()
    for imagem, pares in por_imagem.items():
        pixels= cv2.imread(str(anon_dir / Path(imagem.caminho_anon).name)) if imagem.caminho_anon else None
        if pixels is None:
            ignorados["ficheiro em falta"]+= len(pares)
            continue
        altura, largura= pixels.shape[:2]
        if imagem.camera_type == "spherical":
            vistas= list(views(pixels, LADO_VISTA))
            recortados= []
            for n, (obs, classe) in enumerate(pares):
                recorte= _recorte_do_panorama(vistas, obs.bbox, largura, altura, classe)
                if recorte is None:
                    ignorados["panorama fora das vistas"]+= 1
                else:
                    recortados.append((n, classe, recorte))
        else:
            itens= [
                {"caixa": [obs.bbox[0] / largura, obs.bbox[1] / altura, obs.bbox[2] / largura, obs.bbox[3] / altura], "classe": c}
                for obs, c in pares
            ]
            recortados= recortes_de(pixels, itens)
        for n, classe, recorte in recortados:
            destino= saida / "recortes" / divisao_de(imagem.id_fonte) / classe
            destino.mkdir(parents=True, exist_ok=True)
            nome= f"{imagem.fonte}_{imagem.id_fonte}_{pares[n][0].id}.jpg"
            if not cv2.imwrite(str(destino / nome), recorte, [cv2.IMWRITE_JPEG_QUALITY, QUALIDADE_JPEG]):
                raise OSError(f"Não foi possível gravar o recorte {nome}")
            contagem[classe]+= 1
    return contagem, ignorados


def referencia(elementos: list[Elemento], campos: dict[int, set[str]]) -> dict:
    features= []
    for elemento in elementos:
        if elemento.geom is None or not posicao_do_tecnico(campos.get(elemento.id, set()), elemento.estado):
            continue
        ponto= to_shape(elemento.geom)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [ponto.x, ponto.y]},
                "properties": {
                    "classe": elemento.classe,
                    "categoria": elemento.categoria,
                    "analise_id": elemento.analise_id,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def main(argv: list[str] | None= None) -> int:
    parser= argparse.ArgumentParser(prog="python -m training.correcoes")
    parser.add_argument("--categoria", default="iluminacao")
    parser.add_argument("--saida", default=None, help="por omissão data/datasets/correcoes_<categoria>")
    parser.add_argument("--anon-dir", default="data/anon")
    parser.add_argument("--classes", default="config/classes.yaml")
    parser.add_argument("--analise", action="append", default=[], help="código da análise (repetível); por omissão todas")
    parser.add_argument("--referencia", default=None, help="GeoJSON com as posições indicadas pelo técnico")
    args= parser.parse_args(argv)
    load_dotenv(".env")
    saida= Path(args.saida or f"data/datasets/correcoes_{args.categoria}")
    try:
        classes= load_classes(Path(args.classes))
        if args.categoria not in classes.categorias:
            raise ErroPipeline(f"Categoria desconhecida: {args.categoria}")
        url_bd= os.environ.get("DATABASE_URL", "").strip()
        if not url_bd:
            raise ErroPipeline("Variável de ambiente DATABASE_URL em falta. Ver .env.example.")
        with Session(create_engine(url_bd)) as sessao:
            elementos= _elementos(sessao, args.analise)
            campos= _campos(sessao)
            gerais= set(classes.categorias[args.categoria].gerais)
            contagem, ignorados= exportar_recortes(
                elementos, campos, args.categoria, gerais, Path(args.anon_dir), saida
            )
            print(f"Elementos revistos: {Counter(e.estado for e in elementos)}")
            print(f"Recortes gravados em {saida}: {dict(contagem)}")
            if ignorados:
                print(f"Observações ignoradas: {dict(ignorados)}", file=sys.stderr)
            if args.referencia:
                dados= referencia(elementos, campos)
                Path(args.referencia).write_text(json.dumps(dados), encoding="utf-8")
                print(f"Referência do técnico: {len(dados['features'])} elementos em {args.referencia}")
    except (ErroPipeline, OSError, SQLAlchemyError) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
