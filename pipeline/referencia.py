import argparse
import json
import math
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from pyproj import Transformer

from pipeline.config import load_municipio
from pipeline.errors import ErroPipeline
from pipeline.ingest.mapillary import tiles
from pipeline.rotulos_mapillary import classificar

URL= "https://graph.mapillary.com/map_features"
PASSO_GRAUS= 0.005
LIMITE= 2000
RAIO_JUNTAR_M= 3.0
GENERICAS= {"outro", "contentor"}


def obter_features(bbox: tuple[float, float, float, float], token: str, sessao: requests.Session | None= None) -> list[dict]:
    sessao= sessao or requests.Session()
    sessao.headers["Authorization"]= f"OAuth {token}"
    vistas= {}
    for tile in tiles(bbox, PASSO_GRAUS):
        resposta= sessao.get(
            URL,
            params={
                "bbox": ",".join(f"{v:.6f}" for v in tile),
                "fields": "id,object_value,geometry,first_seen_at,last_seen_at",
                "limit": LIMITE,
            },
            timeout=60,
        )
        if resposta.status_code != 200:
            raise ErroPipeline(f"Mapillary respondeu {resposta.status_code} ao pedir map features")
        dados= resposta.json().get("data", [])
        if len(dados) >= LIMITE:
            raise ErroPipeline("Demasiadas map features num só pedido: reduzir PASSO_GRAUS")
        for item in dados:
            vistas[item["id"]]= item
    lon_min, lat_min, lon_max, lat_max= bbox
    return [
        item
        for item in vistas.values()
        if lon_min <= item["geometry"]["coordinates"][0] <= lon_max
        and lat_min <= item["geometry"]["coordinates"][1] <= lat_max
    ]


def juntar(pontos: list[dict], crs_metrico: str, raio_m: float= RAIO_JUNTAR_M) -> list[dict]:
    para_metros= Transformer.from_crs("EPSG:4326", crs_metrico, always_xy=True)
    ordenados= sorted(pontos, key=lambda p: p["classe"] in GENERICAS)
    ficam= []
    for ponto in ordenados:
        xy= para_metros.transform(ponto["lon"], ponto["lat"])
        perto= any(
            outro["categoria"] == ponto["categoria"]
            and (ponto["classe"] in GENERICAS or outro["classe"] == ponto["classe"])
            and math.dist(outro["xy"], xy) <= raio_m
            for outro in ficam
        )
        if not perto:
            ficam.append({**ponto, "xy": xy})
    return [{k: v for k, v in p.items() if k != "xy"} for p in ficam]


def para_pontos(features: list[dict], incluir_costas: bool= False) -> list[dict]:
    pontos= []
    for item in features:
        decisao= classificar(item["object_value"], incluir_costas)
        if decisao is None:
            continue
        lon, lat= item["geometry"]["coordinates"][:2]
        pontos.append(
            {
                "categoria": decisao[0],
                "classe": decisao[1],
                "lon": lon,
                "lat": lat,
                "valor_original": item["object_value"],
                "id_mapillary": item["id"],
            }
        )
    return pontos


def para_geojson(pontos: list[dict]) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
                "properties": {
                    "categoria": p["categoria"],
                    "classe": p["classe"],
                    "origem": "mapillary_map_features",
                    "valor_original": p["valor_original"],
                    "id_mapillary": p["id_mapillary"],
                },
            }
            for p in pontos
        ],
    }


def main(argv: list[str] | None= None) -> int:
    parser= argparse.ArgumentParser(prog="python -m pipeline.referencia")
    parser.add_argument("--municipio", required=True, help="ficheiro municipio.yaml")
    parser.add_argument("--saida", required=True, help="GeoJSON de referência a escrever")
    parser.add_argument("--incluir-costas", action="store_true", help="conta sinais vistos de trás")
    args= parser.parse_args(argv)
    load_dotenv()
    token= os.environ.get("MAPILLARY_TOKEN", "").strip()
    try:
        if not token:
            raise ErroPipeline("Variável de ambiente MAPILLARY_TOKEN em falta. Ver .env.example.")
        municipio= load_municipio(Path(args.municipio))
        features= obter_features(municipio.bbox, token)
        pontos= juntar(para_pontos(features, args.incluir_costas), municipio.crs_metrico)
    except (ErroPipeline, requests.RequestException) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    Path(args.saida).write_text(json.dumps(para_geojson(pontos), ensure_ascii=False, indent=1), encoding="utf-8")
    contagem= {}
    for p in pontos:
        contagem[(p["categoria"], p["classe"])]= contagem.get((p["categoria"], p["classe"]), 0) + 1
    print(f"{len(pontos)} elementos de referência em {args.saida}")
    for (categoria, classe), n in sorted(contagem.items()):
        print(f"  {categoria}/{classe}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
