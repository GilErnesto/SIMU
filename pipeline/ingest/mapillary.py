import math
from collections.abc import Iterator
from datetime import UTC, datetime

import cv2
import numpy as np
import requests

from pipeline.errors import ErroPipeline
from pipeline.models import ImageRecord

URL= "https://graph.mapillary.com/images"
CAMPOS= "id,computed_geometry,computed_compass_angle,camera_type,captured_at,creator,thumb_2048_url"
LICENCA= "CC BY-SA 4.0"
PASSO_GRAUS= 0.02
LIMITE_POR_TILE= 2000
TIMEOUT_S= 30


def tiles(
    bbox: tuple[float, float, float, float], passo: float= PASSO_GRAUS
) -> Iterator[tuple[float, float, float, float]]:
    lon_min, lat_min, lon_max, lat_max= bbox
    colunas= math.ceil(round((lon_max - lon_min) / passo, 6))
    linhas= math.ceil(round((lat_max - lat_min) / passo, 6))
    for i in range(colunas):
        for j in range(linhas):
            yield (
                lon_min + i * passo,
                lat_min + j * passo,
                min(lon_min + (i + 1) * passo, lon_max),
                min(lat_min + (j + 1) * passo, lat_max),
            )


def parse(item: dict) -> ImageRecord | None:
    geometria= item.get("computed_geometry")
    angulo= item.get("computed_compass_angle")
    url_imagem= item.get("thumb_2048_url")
    if not geometria or angulo is None or not url_imagem:
        return None
    lon, lat= geometria["coordinates"]
    criador= item.get("creator") or {}
    autor= criador.get("username") or str(criador.get("id") or "") or "desconhecido"
    capturada= item.get("captured_at")
    return ImageRecord(
        fonte="mapillary",
        id_fonte=str(item["id"]),
        autor=autor,
        licenca=LICENCA,
        url_origem=f"https://www.mapillary.com/app/?pKey={item['id']}",
        capturada_em=None
        if capturada is None
        else datetime.fromtimestamp(capturada / 1000, tz=UTC),
        lon=lon,
        lat=lat,
        heading=float(angulo),
        camera_type=item.get("camera_type") or "perspective",
        url_imagem=url_imagem,
    )


def fetch_images(
    bbox: tuple[float, float, float, float], token: str, sessao: requests.Session | None= None
) -> list[ImageRecord]:
    sessao= sessao or requests.Session()
    sessao.headers["Authorization"]= f"OAuth {token}"
    por_id= {}
    for tile in tiles(bbox):
        parametros= {
            "bbox": ",".join(str(v) for v in tile),
            "fields": CAMPOS,
            "limit": LIMITE_POR_TILE,
        }
        try:
            resposta= sessao.get(URL, params=parametros, timeout=TIMEOUT_S)
            resposta.raise_for_status()
        except requests.RequestException as erro:
            raise ErroPipeline(f"Falha ao contactar o Mapillary: {erro}") from erro
        for item in resposta.json().get("data", []):
            registo= parse(item)
            if registo is not None:
                por_id[registo.id_fonte]= registo
    return list(por_id.values())


def download(registo: ImageRecord, sessao: requests.Session | None= None) -> np.ndarray:
    sessao= sessao or requests.Session()
    try:
        resposta= sessao.get(registo.url_imagem, timeout=TIMEOUT_S)
        resposta.raise_for_status()
    except requests.RequestException as erro:
        raise ErroPipeline(f"Falha ao descarregar a imagem {registo.id}: {erro}") from erro
    imagem= cv2.imdecode(np.frombuffer(resposta.content, np.uint8), cv2.IMREAD_COLOR)
    if imagem is None:
        raise ErroPipeline(f"Imagem {registo.id} não pôde ser descodificada")
    return imagem
