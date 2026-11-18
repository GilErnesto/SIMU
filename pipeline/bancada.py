import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from pathlib import Path

import cv2
from dotenv import load_dotenv
from geoalchemy2.shape import to_shape
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from pipeline import checkpoint, evaluate
from pipeline.catalog import analises
from pipeline.catalog.write import Imagem, element_confidence
from pipeline.config import Classes, calibrar_confianca, load_classes, load_municipio
from pipeline.detect.panorama import detect_panorama
from pipeline.errors import ErroPipeline
from pipeline.geolocate.locate import locate
from pipeline.models import Element, ImageRecord
from pipeline.run import CABECA_ILUMINACAO, CABECA_SINAL, _detetor

RAIO_COBERTURA_M= 30.0


def imagens_da_analise(sessao: Session, token: str, pasta_anon: Path) -> list[ImageRecord]:
    analise= analises.obter_por_token(sessao, token)
    if analise is None:
        raise ErroPipeline(f"Análise desconhecida: {token}")
    registos= []
    for linha in sessao.scalars(select(Imagem).where(Imagem.analise_id == analise.id).order_by(Imagem.id)):
        if not linha.caminho_anon:
            continue
        ponto= to_shape(linha.geom)
        registos.append(
            ImageRecord(
                fonte=linha.fonte,
                id_fonte=linha.id_fonte,
                autor=linha.autor,
                licenca=linha.licenca,
                url_origem=linha.url_origem,
                capturada_em=linha.capturada_em,
                lon=ponto.x,
                lat=ponto.y,
                heading=linha.heading or 0.0,
                camera_type=linha.camera_type or "perspective",
                url_imagem="",
                caminho_anon=str(pasta_anon / Path(linha.caminho_anon).name),
            )
        )
    return registos


def amostrar(registos: list[ImageRecord], maximo: int | None) -> list[ImageRecord]:
    ordenados= sorted(registos, key=lambda r: r.id_fonte)
    if maximo is None or len(ordenados) <= maximo:
        return ordenados
    escolhidas= sorted(ordenados, key=lambda r: hashlib.sha1(r.id_fonte.encode()).hexdigest())[:maximo]
    return sorted(escolhidas, key=lambda r: r.id_fonte)


def imagens_do_mapillary(
    registos: list[ImageRecord], pasta_anon: Path, carregar_anonimizador, baixar= None, saida=sys.stderr
) -> list[ImageRecord]:
    from pipeline.anonymize.egoblur import caminho_anon, save_anon
    from pipeline.ingest import mapillary

    baixar= baixar or mapillary.download
    anonimizador= None
    prontas= []
    for registo in registos:
        caminho= caminho_anon(pasta_anon, registo)
        if not caminho.is_file():
            try:
                original= baixar(registo)
            except ErroPipeline as erro:
                print(f"Aviso: {erro}", file=saida)
                continue
            anonimizador= anonimizador or carregar_anonimizador()
            save_anon(anonimizador(original), pasta_anon, registo)
            del original
        registo.caminho_anon= str(caminho)
        prontas.append(registo)
    return prontas


def detetar(registos: list[ImageRecord], detetor, cache: Path, saida=sys.stderr) -> dict:
    feitas= checkpoint.load(cache)
    inicio= time.time()
    for n, registo in enumerate(registos, 1):
        if registo.id_fonte in feitas:
            continue
        imagem= cv2.imread(registo.caminho_anon)
        if imagem is None:
            print(f"Aviso: imagem em falta {registo.caminho_anon}", file=saida)
            continue
        registo.height, registo.width= imagem.shape[:2]
        if registo.camera_type == "spherical":
            deteccoes= detect_panorama(detetor, registo.id, imagem)
        else:
            deteccoes= detetor.detect(registo.id, imagem)
        checkpoint.append(cache, registo, deteccoes)
        feitas[registo.id_fonte]= (registo, deteccoes)
        if n % 25 == 0:
            print(f"[{n}/{len(registos)}] {n / (time.time() - inicio):.2f} imagens/s", file=saida, flush=True)
    return feitas


def elementos_geojson(elementos: list[Element], classes: Classes | None= None) -> dict:
    features= []
    for elemento in elementos:
        confiancas= [o.detection.confidence for o in elemento.observations]
        if classes is not None:
            confiancas= [
                calibrar_confianca(classes.categorias[elemento.category], c) for c in confiancas
            ]
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [elemento.lon, elemento.lat]},
                "properties": {
                    "categoria": elemento.category,
                    "classe": elemento.class_name,
                    "confianca": element_confidence(statistics.fmean(confiancas), len(confiancas)),
                    "n_observacoes": len(confiancas),
                    "metodo_geo": elemento.metodo_geo,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def imagens_geojson(registos: list[ImageRecord]) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [r.lon, r.lat]},
                "properties": {"id_fonte": r.id_fonte},
            }
            for r in registos
        ],
    }


def main(argv: list[str] | None= None) -> int:
    parser= argparse.ArgumentParser(prog="python -m pipeline.bancada")
    parser.add_argument("--municipio", default="config/municipio.yaml")
    parser.add_argument("--analise", default="inicial", help="token da análise cujas imagens se usam")
    parser.add_argument("--nome", required=True, help="nome da experiência (pasta de resultados)")
    parser.add_argument("--detetor", choices=("auto", "owlv2", "yolo"), default="auto")
    parser.add_argument("--pesos", default="models/detetor.pt")
    parser.add_argument("--limiar", type=float, default=0.2)
    parser.add_argument("--limiar-classe", type=float, default=0.3)
    parser.add_argument("--cabeca-sinal", default=CABECA_SINAL)
    parser.add_argument("--cabeca-iluminacao", default=CABECA_ILUMINACAO)
    parser.add_argument("--sem-refinar", action="store_true")
    parser.add_argument("--anon-dir", help="por omissão data/anon (catálogo) ou data/avaliacao/imagens")
    parser.add_argument("--fonte", choices=("catalogo", "mapillary"), default="catalogo")
    parser.add_argument("--max-imagens", type=int, help="amostra estável das imagens do Mapillary")
    parser.add_argument("--classes", default="config/classes.yaml")
    parser.add_argument("--egoblur", default="models/egoblur")
    parser.add_argument("--resultados", default="data/avaliacao")
    parser.add_argument("--referencia", help="GeoJSON ou CSV de referência para avaliar logo")
    parser.add_argument("--tolerancia", type=float, default=15.0)
    parser.add_argument("--raio-cobertura", type=float, default=RAIO_COBERTURA_M)
    args= parser.parse_args(argv)
    load_dotenv()
    try:
        municipio= load_municipio(Path(args.municipio))
        classes= load_classes(Path(args.classes))
        if args.fonte == "mapillary":
            from pipeline.anonymize.egoblur import Anonymizer
            from pipeline.ingest import mapillary

            token= os.environ.get("MAPILLARY_TOKEN", "").strip()
            if not token:
                raise ErroPipeline("Variável de ambiente MAPILLARY_TOKEN em falta. Ver .env.example.")
            listadas= amostrar(mapillary.fetch_images(municipio.bbox, token), args.max_imagens)
            registos= imagens_do_mapillary(
                listadas,
                Path(args.anon_dir or "data/avaliacao/imagens"),
                lambda: Anonymizer.from_dir(Path(args.egoblur)),
            )
        else:
            url_bd= os.environ.get("DATABASE_URL", "").strip()
            if not url_bd:
                raise ErroPipeline("Variável de ambiente DATABASE_URL em falta. Ver .env.example.")
            with Session(create_engine(url_bd)) as sessao:
                registos= imagens_da_analise(sessao, args.analise, Path(args.anon_dir or "data/anon"))
        pasta= Path(args.resultados) / args.nome
        pasta.mkdir(parents=True, exist_ok=True)
        cache= pasta / "deteccoes.jsonl"
        feitas= checkpoint.load(cache)
        detetor= None if all(r.id_fonte in feitas for r in registos) else _detetor(args, classes, limiares=False)
        feitas= detetar(registos, detetor, cache) if detetor is not None else feitas
        pedidas= {r.id_fonte for r in registos}
        feitas= {k: v for k, v in feitas.items() if k in pedidas}
        imagens= [registo for registo, _ in feitas.values()]
        deteccoes= [
            d
            for _, lista in feitas.values()
            for d in lista
            if d.confidence >= classes.categorias[d.category].limiar_detecao
        ]
        elementos= locate(imagens, deteccoes, municipio, classes)
        previsto= elementos_geojson(elementos, classes)
        (pasta / "previsto.geojson").write_text(json.dumps(previsto), encoding="utf-8")
        (pasta / "imagens.geojson").write_text(json.dumps(imagens_geojson(imagens)), encoding="utf-8")
        print(f"{len(imagens)} imagens, {len(deteccoes)} deteções, {len(elementos)} elementos em {pasta}")
        if args.referencia:
            cobertura= imagens_geojson(imagens)
            referencia= evaluate.cobertos(
                evaluate.ler(args.referencia), cobertura, municipio.crs_metrico, args.raio_cobertura
            )
            avaliado= evaluate.cobertos(previsto, cobertura, municipio.crs_metrico, args.raio_cobertura)
            relatorio= []
            for nivel in ("categoria", "classe"):
                resultados= evaluate.evaluate(
                    avaliado, referencia, municipio.crs_metrico, args.tolerancia, nivel=nivel
                )
                relatorio.append(evaluate.to_markdown(resultados, args.tolerancia, nivel))
            relatorio.append(
                evaluate.linha_do_tipo(
                    *evaluate.exatidao_do_tipo(avaliado, referencia, municipio.crs_metrico, args.tolerancia)
                )
            )
            texto= "\n".join(relatorio)
            (pasta / "resultado.md").write_text(texto, encoding="utf-8")
            print(texto)
    except ErroPipeline as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
