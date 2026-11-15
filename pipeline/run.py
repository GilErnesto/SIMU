import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pipeline.anonymize.egoblur import Anonymizer, save_anon
from pipeline.catalog.write import ensure_schema, known_image_ids, write_catalog
from pipeline.config import load_classes, load_municipio
from pipeline.detect.infer import Detector
from pipeline.errors import ErroPipeline
from pipeline.geolocate.locate import locate
from pipeline.ingest import mapillary

FONTES= ("mapillary",)


def _variavel(nome: str) -> str:
    valor= os.environ.get(nome, "").strip()
    if not valor:
        raise ErroPipeline(f"Variável de ambiente {nome} em falta. Ver .env.example.")
    return valor


def _detetor(args: argparse.Namespace, classes):
    if args.detetor == "yolo":
        return Detector.from_weights(Path(args.pesos), classes)
    from pipeline.detect.owl import OwlDetector

    return OwlDetector.load(classes, limiar=args.limiar)


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
    with Session(engine) as sessao:
        conhecidas= known_image_ids(sessao, args.fonte)
        novas= [
            r for r in mapillary.fetch_images(municipio.bbox, token) if r.id_fonte not in conhecidas
        ]
        deteccoes= []
        for registo in novas:
            original= mapillary.download(registo)
            anonima= anonimizador(original)
            del original
            registo.height, registo.width= anonima.shape[:2]
            registo.caminho_anon= save_anon(anonima, Path(args.anon_dir), registo)
            deteccoes.extend(detetor.detect(registo.id, anonima))
        elementos= locate(novas, deteccoes, municipio, classes)
        write_catalog(sessao, classes, novas, elementos)
        sessao.commit()
    print(f"{len(novas)} imagens novas, {len(deteccoes)} deteções, {len(elementos)} elementos.")
    return 0


def main(argv: list[str] | None= None) -> int:
    parser= argparse.ArgumentParser(prog="python -m pipeline.run")
    parser.add_argument("--municipio", required=True, help="ficheiro municipio.yaml")
    parser.add_argument("--fonte", choices=FONTES, default="mapillary")
    parser.add_argument("--detetor", choices=("owlv2", "yolo"), default="owlv2")
    parser.add_argument("--limiar", type=float, default=0.2, help="confiança mínima do OWLv2")
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
