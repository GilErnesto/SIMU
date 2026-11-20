import argparse
import os
import shutil
import sys
import time
import traceback
from collections.abc import Callable
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pipeline.anonymize.egoblur import Anonymizer
from pipeline.catalog import analises, reportes
from pipeline.catalog.write import Analise, ensure_schema, known_image_ids, write_catalog
from pipeline.config import Classes, Municipio, aplicar_bbox, load_classes, load_municipio
from pipeline.errors import ErroPipeline
from pipeline.geolocate.locate import locate
from pipeline.ingest import mapillary, uploads
from pipeline.run import CABECA_SINAL, NOME_CHECKPOINT, _detetor, _variavel, pesos_padrao, processar

INTERVALO_S= 1.0
PASSO_PROGRESSO= 5


def _progresso(sessao: Session, analise: Analise) -> Callable[[int, int], None]:
    ultimo= {"n": 0}

    def progredir(feitas: int, total: int) -> None:
        if feitas == total or feitas - ultimo["n"] >= PASSO_PROGRESSO:
            ultimo["n"]= feitas
            analises.registar_progresso(sessao, analise, feitas, total)

    return progredir


def _gravar(
    sessao: Session,
    analise: Analise,
    feitas: dict,
    falhas: list[str],
    municipio: Municipio,
    classes: Classes,
    avisos: list[str],
) -> None:
    imagens= [registo for registo, _ in feitas.values()]
    deteccoes= [d for _, lista in feitas.values() for d in lista]
    elementos= locate(imagens, deteccoes, municipio, classes)
    write_catalog(sessao, classes, imagens, elementos, analise_id=analise.id)
    sessao.commit()
    if falhas:
        avisos.append(f"{len(falhas)} imagens não puderam ser lidas")
    analises.atualizar_contagens(sessao, analise)
    analises.concluir(sessao, analise, analise.n_elementos, avisos)


MAX_IMAGENS_ZONA= 1500


def _limite_zona() -> int:
    try:
        return int(os.environ.get("MAX_IMAGENS_ZONA", MAX_IMAGENS_ZONA))
    except ValueError:
        return MAX_IMAGENS_ZONA


def _processar_zona(
    sessao: Session,
    analise: Analise,
    anonimizador,
    detetor,
    municipio: Municipio,
    classes: Classes,
    pasta_anon: Path,
    saida=sys.stderr,
) -> bool:
    try:
        token= _variavel("MAPILLARY_TOKEN")
    except ErroPipeline:
        analises.falhar(sessao, analise, "O worker não tem o MAPILLARY_TOKEN configurado")
        return False
    avisos= list(analise.avisos or [])
    try:
        zona= aplicar_bbox(municipio, ",".join(str(valor) for valor in analise.parametros["bbox"]))
        listadas= mapillary.fetch_images(zona.bbox, token)
        if not listadas:
            analises.falhar(sessao, analise, "Não há imagens do Mapillary nesta zona")
            return False
        conhecidas= known_image_ids(sessao, "mapillary")
        novas= [registo for registo in listadas if registo.id_fonte not in conhecidas]
        if not novas:
            erro= "A imagem desta zona já está noutra análise" if len(listadas) == 1 else f"As {len(listadas)} imagens desta zona já estão noutra análise"
            analises.falhar(sessao, analise, erro)
            return False
        limite= _limite_zona()
        if len(novas) > limite:
            analises.falhar(
                sessao,
                analise,
                f"A zona tem {len(novas)} imagens, mais do que o máximo de {limite} por análise. Escolha uma zona mais pequena.",
            )
            return False
        repetidas= len(listadas) - len(novas)
        if repetidas:
            avisos.append(f"{repetidas} imagem já existia noutra análise e ficou de fora" if repetidas == 1 else f"{repetidas} imagens já existiam noutra análise e ficaram de fora")
        analises.registar_progresso(sessao, analise, 0, len(novas))
        feitas, falhas= processar(
            novas,
            anonimizador,
            detetor,
            pasta_anon,
            pasta_anon / NOME_CHECKPOINT,
            saida=saida,
            ao_progredir=_progresso(sessao, analise),
        )
        _gravar(sessao, analise, feitas, falhas, zona, classes, avisos)
    except Exception as erro:
        traceback.print_exc(file=saida)
        analises.falhar(sessao, analise, f"{type(erro).__name__}: {erro}", avisos)
        return False
    return True


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
    if (analise.parametros or {}).get("fonte") == "mapillary":
        return _processar_zona(sessao, analise, anonimizador, detetor, municipio, classes, pasta_anon, saida)
    pasta= pasta_raw / analise.token
    if not pasta.is_dir():
        analises.falhar(sessao, analise, "Os ficheiros enviados já não existem no servidor")
        return False
    avisos= list(analise.avisos or [])
    try:
        registos, novos_avisos= uploads.carregar(pasta, analise.token, analise.parametros or {})
        avisos.extend(novos_avisos)
        if not registos:
            motivo= next(
                (a for a in novos_avisos if "mais do que o máximo" in a),
                "não há fotografias nem vídeos que se consigam ler",
            )
            analises.falhar(sessao, analise, f"Nenhuma imagem utilizável: {motivo}", avisos)
            return False
        analises.registar_progresso(sessao, analise, 0, len(registos))
        feitas, falhas= processar(
            registos,
            anonimizador,
            detetor,
            pasta_anon,
            pasta / NOME_CHECKPOINT,
            uploads.ler_ficheiro,
            saida=saida,
            ao_progredir=_progresso(sessao, analise),
        )
        _gravar(sessao, analise, feitas, falhas, municipio, classes, avisos)
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
    parser.add_argument("--detetor", choices=("auto", "owlv2", "yolo"), default="auto")
    parser.add_argument("--limiar", type=float, default=0.25)
    parser.add_argument("--sem-refinar", action="store_true")
    parser.add_argument("--limiar-classe", type=float, default=0.3)
    parser.add_argument("--cabeca-sinal", default=CABECA_SINAL)
    parser.add_argument("--pesos", default=pesos_padrao())
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
                # Citizens wait on screen for their photo: those go before any analysis.
                reporte= reportes.reclamar_foto(sessao)
                if reporte is not None:
                    ok= reportes.processar_foto(
                        sessao, reporte, anonimizador, detetor, Path(args.raw_dir), Path(args.anon_dir)
                    )
                    print(f"Reporte {reporte.token}: {'fotografia pronta' if ok else 'falhou'}.", flush=True)
                    continue
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
