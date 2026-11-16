import argparse
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pipeline import checkpoint
from pipeline.anonymize.egoblur import Anonymizer, caminho_anon, save_anon
from pipeline.catalog.write import ensure_schema, known_image_ids, write_catalog
from pipeline.config import load_classes, load_municipio
from pipeline.detect.infer import Detector
from pipeline.detect.panorama import detect_panorama
from pipeline.errors import ErroPipeline
from pipeline.geolocate.locate import locate
from pipeline.ingest import mapillary
from pipeline.models import Detection, ImageRecord

FONTES= ("mapillary",)
PASSO_PROGRESSO= 25
NOME_CHECKPOINT= "checkpoint.jsonl"


def _variavel(nome: str) -> str:
    valor= os.environ.get(nome, "").strip()
    if not valor:
        raise ErroPipeline(f"Variável de ambiente {nome} em falta. Ver .env.example.")
    return valor


def _detetor(args: argparse.Namespace, classes):
    if args.detetor == "yolo":
        return Detector.from_weights(Path(args.pesos), classes)
    from pipeline.detect.owl import OwlDetector

    detetor= OwlDetector.load(classes, limiar=args.limiar)
    if args.sem_refinar:
        return detetor
    from pipeline.detect.refinar import DuasFases, Refinador

    return DuasFases(detetor, Refinador.load(classes, limiar=args.limiar_classe), classes)


def _anonima_em_disco(registo: ImageRecord, pasta_anon: Path) -> np.ndarray | None:
    caminho= caminho_anon(pasta_anon, registo)
    if not caminho.is_file():
        return None
    return cv2.imread(str(caminho))


def processar(
    imagens: list[ImageRecord],
    anonimizador: Callable[[np.ndarray], np.ndarray],
    detetor,
    pasta_anon: Path,
    ficheiro_checkpoint: Path,
    baixar: Callable[[ImageRecord], np.ndarray]= mapillary.download,
    saida=sys.stderr,
) -> tuple[dict[str, tuple[ImageRecord, list[Detection]]], list[str]]:
    guardadas= checkpoint.load(ficheiro_checkpoint)
    resultado= {}
    falhas= []
    inicio= time.time()
    for n, registo in enumerate(imagens, 1):
        if registo.id_fonte in guardadas:
            resultado[registo.id_fonte]= guardadas[registo.id_fonte]
            continue
        anonima= _anonima_em_disco(registo, pasta_anon)
        if anonima is None:
            try:
                original= baixar(registo)
            except ErroPipeline as erro:
                falhas.append(registo.id_fonte)
                print(f"Aviso: {erro}", file=saida)
                continue
            anonima= anonimizador(original)
            del original
            registo.caminho_anon= save_anon(anonima, pasta_anon, registo)
        else:
            registo.caminho_anon= str(caminho_anon(pasta_anon, registo))
        registo.height, registo.width= anonima.shape[:2]
        if registo.camera_type == "spherical":
            deteccoes= detect_panorama(detetor, registo.id, anonima)
        else:
            deteccoes= detetor.detect(registo.id, anonima)
        checkpoint.append(ficheiro_checkpoint, registo, deteccoes)
        resultado[registo.id_fonte]= (registo, deteccoes)
        if n % PASSO_PROGRESSO == 0:
            ritmo= n / (time.time() - inicio)
            print(f"[{n}/{len(imagens)}] {ritmo:.2f} imagens/s, {len(falhas)} falhas", file=saida, flush=True)
    return resultado, falhas


def run(args: argparse.Namespace) -> int:
    municipio_path= Path(args.municipio)
    municipio= load_municipio(municipio_path)
    classes= load_classes(municipio_path.parent / "classes.yaml")
    token= _variavel("MAPILLARY_TOKEN")
    url_bd= _variavel("DATABASE_URL")
    anonimizador= Anonymizer.from_dir(Path(args.egoblur))
    detetor= _detetor(args, classes)
    engine= create_engine(url_bd)
    ensure_schema(engine)
    pasta_anon= Path(args.anon_dir)
    with Session(engine) as sessao:
        conhecidas= known_image_ids(sessao, args.fonte)
        novas= [
            r for r in mapillary.fetch_images(municipio.bbox, token) if r.id_fonte not in conhecidas
        ]
        feitas, falhas= processar(
            novas, anonimizador, detetor, pasta_anon, pasta_anon / NOME_CHECKPOINT
        )
        imagens= [registo for registo, _ in feitas.values()]
        deteccoes= [d for _, lista in feitas.values() for d in lista]
        print("A calcular posições e a escrever o catálogo.", file=sys.stderr, flush=True)
        elementos= locate(imagens, deteccoes, municipio, classes)
        write_catalog(sessao, classes, imagens, elementos)
        sessao.commit()
    print(
        f"{len(imagens)} imagens novas, {len(deteccoes)} deteções, {len(elementos)} elementos, "
        f"{len(falhas)} imagens ignoradas por falha de rede."
    )
    return 0


def main(argv: list[str] | None= None) -> int:
    parser= argparse.ArgumentParser(prog="python -m pipeline.run")
    parser.add_argument("--municipio", required=True, help="ficheiro municipio.yaml")
    parser.add_argument("--fonte", choices=FONTES, default="mapillary")
    parser.add_argument("--detetor", choices=("owlv2", "yolo"), default="owlv2")
    parser.add_argument("--limiar", type=float, default=0.2, help="confiança mínima do OWLv2")
    parser.add_argument("--sem-refinar", action="store_true", help="só os três grandes, sem tipo")
    parser.add_argument("--limiar-classe", type=float, default=0.5, help="confiança mínima do tipo")
    parser.add_argument("--pesos", default="models/detetor.pt", help="pesos YOLO")
    parser.add_argument("--egoblur", default="models/egoblur", help="pasta com os modelos EgoBlur")
    parser.add_argument("--anon-dir", default="data/anon", help="destino das imagens anonimizadas")
    args= parser.parse_args(argv)
    load_dotenv()
    try:
        return run(args)
    except ErroPipeline as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
