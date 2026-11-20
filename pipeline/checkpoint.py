import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from pipeline.models import Detection, ImageRecord


def append(
    caminho: Path, registo: ImageRecord, deteccoes: list[Detection], versao: str | None= None
) -> None:
    imagem= asdict(registo)
    imagem["capturada_em"]= registo.capturada_em.isoformat() if registo.capturada_em else None
    linha= {"imagem": imagem, "deteccoes": [asdict(d) for d in deteccoes]}
    if versao is not None:
        linha["versao"]= versao
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("a", encoding="utf-8") as ficheiro:
        ficheiro.write(json.dumps(linha) + "\n")


def _ler_linha(texto: str, versao: str | None= None) -> tuple[ImageRecord, list[Detection]] | None:
    try:
        dados= json.loads(texto)
        if versao is not None and dados.get("versao") != versao:
            return None
        imagem= dados["imagem"]
        capturada= imagem["capturada_em"]
        imagem["capturada_em"]= datetime.fromisoformat(capturada) if capturada else None
        deteccoes= [
            Detection(**{**d, "bbox_xyxy": tuple(d["bbox_xyxy"])}) for d in dados["deteccoes"]
        ]
        return ImageRecord(**imagem), deteccoes
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def load(
    caminho: Path, versao: str | None= None
) -> dict[str, tuple[ImageRecord, list[Detection]]]:
    if not caminho.exists():
        return {}
    entradas= {}
    for texto in caminho.read_text(encoding="utf-8").splitlines():
        lida= _ler_linha(texto, versao) if texto.strip() else None
        if lida is not None:
            entradas[lida[0].id_fonte]= lida
    return entradas
