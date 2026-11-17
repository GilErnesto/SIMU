import os
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from pipeline.config import Classes, Municipio, load_classes, load_municipio
from pipeline.errors import ErroPipeline


@lru_cache
def get_engine() -> Engine:
    url= os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise ErroPipeline("Variável de ambiente DATABASE_URL em falta. Ver .env.example.")
    return create_engine(url, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as sessao:
        yield sessao


def municipio_path() -> Path:
    return Path(os.environ.get("MUNICIPIO_YAML", "config/municipio.yaml"))


@lru_cache
def get_municipio() -> Municipio:
    return load_municipio(municipio_path())


@lru_cache
def get_classes() -> Classes:
    return load_classes(municipio_path().parent / "classes.yaml")


def anon_dir() -> Path:
    return Path(os.environ.get("ANON_DIR", "data/anon"))


def raw_dir() -> Path:
    return Path(os.environ.get("RAW_DIR", "data/raw"))
