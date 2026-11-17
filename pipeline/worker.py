import argparse
import shutil
import sys
import time
import traceback
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pipeline.anonymize.egoblur import Anonymizer
from pipeline.catalog import analises
from pipeline.catalog.write import Analise, ensure_schema, write_catalog
from pipeline.config import Classes, Municipio, load_classes, load_municipio
from pipeline.errors import ErroPipeline
from pipeline.geolocate.locate import locate
from pipeline.ingest import uploads
from pipeline.run import NOME_CHECKPOINT, _detetor, _variavel, processar

INTERVALO_S= 3.0
PASSO_PROGRESSO= 5


def processar_analise(
    sessao: Session,
    analise: Analise,
    anonimizador,
    detetor,
    municipio: Municipio,
    classes: Classes,
    pasta_raw: Path,
    pasta_anon: Path,
    saida=sys.stderr,
) -> bool:
    pasta= pasta_raw / analise.token
    if not pasta.is_dir():
        analises.falhar(sessao, analise, "Os ficheiros enviados já não existem no servidor")
        return False
    avisos= list(analise.avisos or [])
    try:
        registos, novos_avisos= uploads.carregar(pasta, analise.token, analise.parametros or {})
        avisos.extend(novos_avisos)
        if not registos:
            analises.falhar(
                sessao,
                analise,
                "Nenhuma imagem utilizável: as fotos precisam de GPS e cada vídeo precisa de um GPX",
                avisos,
            )
            return False
        analises.registar_progresso(sessao, analise, 0, len(registos))
        ultimo= {"n": 0}

        def progredir(feitas: int, total: int) -> None:
            if feitas == total or feitas - ultimo["n"] >= PASSO_PROGRESSO:
                ultimo["n"]= feitas
                analises.registar_progresso(sessao, analise, feitas, total)

        feitas, falhas= processar(
            registos,
            anonimizador,
            detetor,
            pasta_anon,
            pasta / NOME_CHECKPOINT,
            uploads.ler_ficheiro,
            saida=saida,
            ao_progredir=progredir,
        )
        imagens= [registo for registo, _ in feitas.values()]
        deteccoes= [d for _, lista in feitas.values() for d in lista]
        elementos= locate(imagens, deteccoes, municipio, classes)
        write_catalog(sessao, classes, imagens, elementos, analise_id=analise.id)
        sessao.commit()
        if falhas:
            avisos.append(f"{len(falhas)} imagens não puderam ser lidas")
        analises.atualizar_contagens(sessao, analise)
        analises.concluir(sessao, analise, analise.n_elementos, avisos)
    except Exception as erro:
        traceback.print_exc(file=saida)
        analises.falhar(sessao, analise, f"{type(erro).__name__}: {erro}", avisos)
        return False
    shutil.rmtree(pasta, ignore_errors=True)
    return True


def main(argv: list[str] | None= None) -> int:
    parser= argparse.ArgumentParser(prog="python -m pipeline.worker")
    parser.add_argument("--municipio", default="config/municipio.yaml")
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--anon-dir", default="data/anon")
    parser.add_argument("--egoblur", default="models/egoblur")
    parser.add_argument("--detetor", choices=("owlv2", "yolo"), default="owlv2")
    parser.add_argument("--limiar", type=float, default=0.25)
    parser.add_argument("--sem-refinar", action="store_true")
    parser.add_argument("--limiar-classe", type=float, default=0.5)
    parser.add_argument("--pesos", default="models/detetor.pt")
    parser.add_argument("--uma-vez", action="store_true", help="processa a fila e termina")
    args= parser.parse_args(argv)
    load_dotenv()
    try:
        municipio_path= Path(args.municipio)
        municipio= load_municipio(municipio_path)
        classes= load_classes(municipio_path.parent / "classes.yaml")
        url_bd= _variavel("DATABASE_URL")
        anonimizador= Anonymizer.from_dir(Path(args.egoblur))
        detetor= _detetor(args, classes)
        engine= create_engine(url_bd)
        ensure_schema(engine)
    except ErroPipeline as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    with Session(engine) as sessao:
        retomadas= analises.recuperar_interrompidas(sessao)
    if retomadas:
        print(f"{retomadas} análises interrompidas voltaram à fila.", flush=True)
    print("Worker pronto. A aguardar análises.", flush=True)
    try:
        while True:
            with Session(engine) as sessao:
                analise= analises.reclamar_proxima(sessao)
                if analise is not None:
                    print(f"A analisar {analise.token} ({analise.nome}).", flush=True)
                    ok= processar_analise(
                        sessao,
                        analise,
                        anonimizador,
                        detetor,
                        municipio,
                        classes,
                        Path(args.raw_dir),
                        Path(args.anon_dir),
                    )
                    print(f"Análise {analise.token}: {'concluída' if ok else 'falhou'}.", flush=True)
                    continue
            if args.uma_vez:
                return 0
            time.sleep(INTERVALO_S)
    except KeyboardInterrupt:
        print("Worker parado.", flush=True)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
