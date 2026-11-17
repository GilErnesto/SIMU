import bisect
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np

from pipeline.errors import ErroPipeline
from pipeline.models import ImageRecord

IMAGENS= {".jpg", ".jpeg", ".png"}
VIDEOS= {".mp4", ".mov", ".m4v", ".avi", ".webm"}
GPX= {".gpx"}
FPS_PADRAO= 2.0
LADO_MAXIMO= 2048
DISTANCIA_MINIMA_M= 0.5
JANELA_RUMO_S= 1.0
CABECALHO_XMP= 131072


def tipo_de(nome: str) -> str | None:
    sufixo= Path(nome).suffix.lower()
    if sufixo in IMAGENS:
        return "imagem"
    if sufixo in VIDEOS:
        return "video"
    if sufixo in GPX:
        return "gpx"
    return None


def nome_original(caminho: Path) -> str:
    return re.sub(r"^\d{4}_", "", caminho.name)


def distancia_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    f1, f2= math.radians(lat1), math.radians(lat2)
    a= math.sin((f2 - f1) / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(a))


def azimute(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    f1, f2= math.radians(lat1), math.radians(lat2)
    delta= math.radians(lon2 - lon1)
    y= math.sin(delta) * math.cos(f2)
    x= math.cos(f1) * math.sin(f2) - math.sin(f1) * math.cos(f2) * math.cos(delta)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _graus(dms, referencia: str) -> float:
    valor= float(dms[0]) + float(dms[1]) / 60 + float(dms[2]) / 3600
    return -valor if referencia in ("S", "W") else valor


def _e_esferica(caminho: Path) -> bool:
    with caminho.open("rb") as ficheiro:
        return b"equirectangular" in ficheiro.read(CABECALHO_XMP)


def ler_exif(caminho: Path) -> dict:
    from PIL import Image

    resultado= {"lat": None, "lon": None, "rumo": None, "data": None, "esferica": False}
    try:
        with Image.open(caminho) as imagem:
            exif= imagem.getexif()
            gps= exif.get_ifd(0x8825)
            data= exif.get_ifd(0x8769).get(36867) or exif.get(306)
    except (OSError, ValueError):
        return resultado
    try:
        if gps.get(2) and gps.get(4):
            resultado["lat"]= _graus(gps[2], gps.get(1, "N"))
            resultado["lon"]= _graus(gps[4], gps.get(3, "E"))
        if gps.get(17) is not None:
            resultado["rumo"]= float(gps[17]) % 360
    except (TypeError, ValueError, IndexError, ZeroDivisionError):
        resultado["lat"]= resultado["lon"]= resultado["rumo"]= None
    if data:
        try:
            resultado["data"]= datetime.strptime(str(data), "%Y:%m:%d %H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            resultado["data"]= None
    resultado["esferica"]= _e_esferica(caminho)
    return resultado


@dataclass(frozen=True)
class Ponto:
    t: datetime
    lat: float
    lon: float


def ler_gpx(caminho: Path) -> list[Ponto]:
    try:
        raiz= ET.parse(caminho).getroot()
    except ET.ParseError as erro:
        raise ErroPipeline(f"GPX inválido: {nome_original(caminho)}") from erro
    pontos= {}
    for elemento in raiz.iter():
        if not elemento.tag.endswith("trkpt"):
            continue
        texto= next((f.text for f in elemento if f.tag.endswith("time") and f.text), None)
        if texto is None:
            continue
        try:
            t= datetime.fromisoformat(texto.strip())
            ponto= Ponto(t if t.tzinfo else t.replace(tzinfo=UTC), float(elemento.attrib["lat"]), float(elemento.attrib["lon"]))
        except (ValueError, KeyError):
            continue
        pontos[ponto.t]= ponto
    ordenados= [pontos[t] for t in sorted(pontos)]
    if len(ordenados) < 2:
        raise ErroPipeline(f"GPX com menos de 2 pontos com hora: {nome_original(caminho)}")
    return ordenados


class Trilho:
    def __init__(self, pontos: list[Ponto]):
        self.pontos= pontos
        self.tempos= [p.t.timestamp() for p in pontos]

    @property
    def inicio(self) -> float:
        return self.tempos[0]

    def posicao(self, segundos: float) -> tuple[float, float] | None:
        if segundos < self.tempos[0] or segundos > self.tempos[-1]:
            return None
        i= min(bisect.bisect_right(self.tempos, segundos), len(self.tempos) - 1)
        a, b= self.pontos[i - 1], self.pontos[i]
        duracao= self.tempos[i] - self.tempos[i - 1]
        fracao= 0.0 if duracao <= 0 else (segundos - self.tempos[i - 1]) / duracao
        return a.lat + (b.lat - a.lat) * fracao, a.lon + (b.lon - a.lon) * fracao

    def rumo(self, segundos: float) -> float | None:
        antes= self.posicao(max(segundos - JANELA_RUMO_S, self.tempos[0]))
        depois= self.posicao(min(segundos + JANELA_RUMO_S, self.tempos[-1]))
        if antes is None or depois is None:
            return None
        if distancia_m(*antes, *depois) < DISTANCIA_MINIMA_M:
            return None
        return azimute(*antes, *depois)


def _reduzir(imagem: np.ndarray) -> np.ndarray:
    altura, largura= imagem.shape[:2]
    maior= max(altura, largura)
    if maior <= LADO_MAXIMO:
        return imagem
    escala= LADO_MAXIMO / maior
    return cv2.resize(imagem, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)


def extrair_frames(caminho: Path, fps: float, pasta: Path) -> list[tuple[float, Path]]:
    captura= cv2.VideoCapture(str(caminho))
    if not captura.isOpened():
        raise ErroPipeline(f"Não foi possível abrir o vídeo {nome_original(caminho)}")
    nativo= captura.get(cv2.CAP_PROP_FPS)
    if not nativo or not math.isfinite(nativo) or nativo <= 0:
        nativo= 30.0
    passo= max(round(nativo / fps), 1)
    pasta.mkdir(parents=True, exist_ok=True)
    frames= []
    indice= 0
    while captura.grab():
        if indice % passo == 0:
            ok, frame= captura.retrieve()
            if ok:
                ficheiro= pasta / f"{caminho.stem}_{indice:07d}.jpg"
                cv2.imwrite(str(ficheiro), _reduzir(frame), [cv2.IMWRITE_JPEG_QUALITY, 92])
                frames.append((indice / nativo, ficheiro))
        indice+= 1
    captura.release()
    return frames


def emparelhar(videos: list[Path], gpxs: list[Path]) -> dict[Path, Path | None]:
    por_nome= {g.stem.split("_", 1)[-1]: g for g in gpxs}
    pares= {}
    for video in videos:
        chave= video.stem.split("_", 1)[-1]
        if chave in por_nome:
            pares[video]= por_nome[chave]
    sem_par_v= [v for v in videos if v not in pares]
    sem_par_g= [g for g in gpxs if g not in pares.values()]
    if len(sem_par_v) == 1 and len(sem_par_g) == 1:
        pares[sem_par_v[0]]= sem_par_g[0]
    return {video: pares.get(video) for video in videos}


def _rumos_em_falta(candidatas: list[tuple[Path, dict]]) -> list[float | None]:
    rumos= [info["rumo"] for _, info in candidatas]
    for i, (_, info) in enumerate(candidatas):
        if rumos[i] is not None:
            continue
        for j in range(i + 1, len(candidatas)):
            outra= candidatas[j][1]
            if distancia_m(info["lat"], info["lon"], outra["lat"], outra["lon"]) >= DISTANCIA_MINIMA_M:
                rumos[i]= azimute(info["lat"], info["lon"], outra["lat"], outra["lon"])
                break
        if rumos[i] is None:
            for j in range(i - 1, -1, -1):
                outra= candidatas[j][1]
                if distancia_m(outra["lat"], outra["lon"], info["lat"], info["lon"]) >= DISTANCIA_MINIMA_M:
                    rumos[i]= azimute(outra["lat"], outra["lon"], info["lat"], info["lon"])
                    break
    return rumos


def carregar(pasta: Path, prefixo: str, parametros: dict) -> tuple[list[ImageRecord], list[str]]:
    ficheiros= sorted(p for p in pasta.iterdir() if p.is_file())
    por_tipo= {"imagem": [], "video": [], "gpx": []}
    for ficheiro in ficheiros:
        tipo= tipo_de(ficheiro.name)
        if tipo:
            por_tipo[tipo].append(ficheiro)
    avisos= []
    registos= []
    n= 0

    candidatas= []
    for caminho in por_tipo["imagem"]:
        info= ler_exif(caminho)
        if info["lat"] is None:
            avisos.append(f"{nome_original(caminho)}: sem GPS na foto, não pode ser localizada")
            continue
        candidatas.append((caminho, info))
    candidatas.sort(key=lambda c: (c[1]["data"] or datetime.min.replace(tzinfo=UTC), c[0].name))
    rumos= _rumos_em_falta(candidatas)
    for (caminho, info), rumo in zip(candidatas, rumos, strict=True):
        if rumo is None:
            avisos.append(f"{nome_original(caminho)}: sem direção na foto e sem fotos vizinhas para a deduzir")
            continue
        n+= 1
        registos.append(
            ImageRecord(
                fonte="upload",
                id_fonte=f"{prefixo}-{n:05d}",
                autor="Utilizador",
                licenca="Dados do utilizador",
                url_origem="",
                capturada_em=info["data"],
                lon=info["lon"],
                lat=info["lat"],
                heading=rumo,
                camera_type="spherical" if info["esferica"] else "perspective",
                url_imagem=str(caminho),
            )
        )

    fps= float(parametros.get("fps") or FPS_PADRAO)
    deslocamento= float(parametros.get("offset_s") or 0.0)
    for video, gpx in emparelhar(por_tipo["video"], por_tipo["gpx"]).items():
        if gpx is None:
            avisos.append(f"{nome_original(video)}: vídeo sem GPX, não pode ser localizado")
            continue
        try:
            trilho= Trilho(ler_gpx(gpx))
            frames= extrair_frames(video, fps, pasta / "frames")
        except ErroPipeline as erro:
            avisos.append(str(erro))
            continue
        avisos.append(
            f"{nome_original(video)}: o início do vídeo foi assumido igual ao início do GPX ({deslocamento:+g} s)"
        )
        usados= 0
        for segundos, ficheiro in frames:
            instante= trilho.inicio + deslocamento + segundos
            posicao= trilho.posicao(instante)
            rumo= trilho.rumo(instante)
            if posicao is None or rumo is None:
                continue
            n+= 1
            usados+= 1
            registos.append(
                ImageRecord(
                    fonte="video",
                    id_fonte=f"{prefixo}-{n:05d}",
                    autor="Utilizador",
                    licenca="Dados do utilizador",
                    url_origem="",
                    capturada_em=datetime.fromtimestamp(instante, UTC),
                    lon=posicao[1],
                    lat=posicao[0],
                    heading=rumo,
                    camera_type="perspective",
                    url_imagem=str(ficheiro),
                )
            )
        if usados == 0:
            avisos.append(f"{nome_original(video)}: nenhum frame coincide com o trilho do GPX (confirme a hora)")
    return registos, avisos


def ler_ficheiro(registo: ImageRecord) -> np.ndarray:
    imagem= cv2.imread(registo.url_imagem)
    if imagem is None:
        raise ErroPipeline(f"Não foi possível ler a imagem {registo.id}")
    return _reduzir(imagem)
