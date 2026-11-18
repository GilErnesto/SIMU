import argparse
import json
import os
import random
import sys
import time
from functools import partial
from pathlib import Path

import requests
from dotenv import load_dotenv

from pipeline.config import load_municipio
from pipeline.errors import ErroPipeline
from pipeline.ingest import mapillary
from pipeline.ingest.vectortile import caixa_normalizada
from pipeline.leitura import ler_adiante
from pipeline.models import ImageRecord
from pipeline.rotulos_mapillary import classificar

URL_DETECOES= "https://graph.mapillary.com/{id}/detections"
TENTATIVAS= 3
ESPERA_S= 2
TIMEOUT_S= 60
MARGEM_GRAUS= 0.001
FICHEIRO= "detecoes.jsonl"


def dentro(registo: ImageRecord, caixas: list[tuple[float, float, float, float]], margem: float) -> bool:
    return any(
        lon_min - margem <= registo.lon <= lon_max + margem and lat_min - margem <= registo.lat <= lat_max + margem
        for lon_min, lat_min, lon_max, lat_max in caixas
    )


def candidatas(
    registos: list[ImageRecord],
    excluidas: list[tuple[float, float, float, float]],
    margem: float= MARGEM_GRAUS,
    semente: int= 0,
) -> list[ImageRecord]:
    ficam= [
        r for r in registos if r.camera_type == "perspective" and not dentro(r, excluidas, margem)
    ]
    ficam.sort(key=lambda r: r.id_fonte)
    random.Random(semente).shuffle(ficam)
    return ficam


def itens_de_sinais(deteccoes: list[dict]) -> list[dict]:
    itens= []
    for deteccao in deteccoes:
        decisao= classificar(deteccao.get("value", ""))
        if decisao is None or decisao[0] != "sinal" or not deteccao.get("geometry"):
            continue
        try:
            caixa= caixa_normalizada(deteccao["geometry"])
        except ErroPipeline:
            continue
        if caixa is None:
            continue
        itens.append({"valor": deteccao["value"], "classe": decisao[1], "caixa": list(caixa)})
    return itens


def _pedir(sessao: requests.Session, url: str, **argumentos) -> requests.Response:
    ultimo= None
    for tentativa in range(TENTATIVAS):
        try:
            resposta= sessao.get(url, timeout=TIMEOUT_S, **argumentos)
            if resposta.status_code == 200:
                return resposta
            ultimo= ErroPipeline(f"Mapillary respondeu {resposta.status_code}")
        except requests.RequestException as erro:
            ultimo= erro
        time.sleep(ESPERA_S * (tentativa + 1))
    raise ErroPipeline(f"Falha ao contactar o Mapillary: {ultimo}")


def processar(registo: ImageRecord, sessao: requests.Session, pasta_raw: Path) -> dict | None:
    try:
        resposta= _pedir(sessao, URL_DETECOES.format(id=registo.id_fonte), params={"fields": "id,value,geometry"})
        itens= itens_de_sinais(resposta.json().get("data", []))
        if not itens:
            return None
        imagem= _pedir(sessao, registo.url_imagem)
    except (ErroPipeline, ValueError):
        return None
    pasta_raw.mkdir(parents=True, exist_ok=True)
    (pasta_raw / f"{registo.id_fonte}.jpg").write_bytes(imagem.content)
    return {
        "id_fonte": registo.id_fonte,
        "autor": registo.autor,
        "licenca": registo.licenca,
        "url_origem": registo.url_origem,
        "itens": itens,
    }


def ja_feitas(ficheiro: Path) -> tuple[set[str], int]:
    if not ficheiro.exists():
        return set(), 0
    ids= set()
    recortes= 0
    for linha in ficheiro.read_text(encoding="utf-8").splitlines():
        try:
            dados= json.loads(linha)
        except json.JSONDecodeError:
            continue
        ids.add(dados["id_fonte"])
        recortes+= len(dados["itens"])
    return ids, recortes


def recolher(
    registos: list[ImageRecord],
    sessao: requests.Session,
    pasta_raw: Path,
    ficheiro: Path,
    alvo_recortes: int,
    max_imagens: int,
    trabalhadores: int,
    saida=sys.stderr,
) -> tuple[int, int]:
    feitas, recortes= ja_feitas(ficheiro)
    pendentes= [r for r in registos if r.id_fonte not in feitas][:max_imagens]
    ficheiro.parent.mkdir(parents=True, exist_ok=True)
    consultadas= 0
    with ficheiro.open("a", encoding="utf-8") as destino:
        for n, (_, resultado) in enumerate(ler_adiante(partial(processar, sessao=sessao, pasta_raw=pasta_raw), pendentes, trabalhadores), 1):
            consultadas= n
            if resultado is not None:
                destino.write(json.dumps(resultado, ensure_ascii=False) + "\n")
                destino.flush()
                recortes+= len(resultado["itens"])
            if n % 200 == 0:
                print(f"[{n}/{len(pendentes)}] {recortes} sinais", file=saida, flush=True)
            if recortes >= alvo_recortes:
                break
    return consultadas, recortes


def main(argv: list[str] | None= None) -> int:
    parser= argparse.ArgumentParser(prog="python -m training.datasets.tipos_mapillary")
    parser.add_argument("--zona", required=True, help="municipio.yaml da zona onde recolher")
    parser.add_argument("--excluir", nargs="*", default=[], help="municipio.yaml de zonas a deixar de fora")
    parser.add_argument("--saida", default="data/datasets/tipos")
    parser.add_argument("--raw", default="data/raw/tipos_mapillary")
    parser.add_argument("--alvo", type=int, default=6000, help="sinais a recolher")
    parser.add_argument("--max-imagens", type=int, default=20000, help="imagens a consultar, no máximo")
    parser.add_argument("--trabalhadores", type=int, default=6)
    args= parser.parse_args(argv)
    load_dotenv()
    token= os.environ.get("MAPILLARY_TOKEN", "").strip()
    try:
        if not token:
            raise ErroPipeline("Variável de ambiente MAPILLARY_TOKEN em falta. Ver .env.example.")
        zona= load_municipio(Path(args.zona))
        excluidas= [load_municipio(Path(c)).bbox for c in args.excluir]
        sessao= requests.Session()
        sessao.headers["Authorization"]= f"OAuth {token}"
        listadas= mapillary.fetch_images(zona.bbox, token, sessao)
        registos= candidatas(listadas, excluidas)
        print(f"{len(listadas)} imagens listadas, {len(registos)} em perspetiva fora das zonas excluídas", file=sys.stderr)
        consultadas, recortes= recolher(
            registos, sessao, Path(args.raw), Path(args.saida) / FICHEIRO, args.alvo, args.max_imagens, args.trabalhadores
        )
    except (ErroPipeline, requests.RequestException) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    print(f"{consultadas} imagens consultadas nesta corrida, {recortes} sinais no total em {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
