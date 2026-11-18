from dataclasses import dataclass, field
from pathlib import Path

import yaml

from pipeline.errors import ErroPipeline


@dataclass(frozen=True)
class Municipio:
    nome: str
    bbox: tuple[float, float, float, float]
    crs_metrico: str


@dataclass(frozen=True)
class Categoria:
    nome: str
    classes: tuple[str, ...]
    raio_dedup_m: float
    altura_m: float
    limiar_especifica: float | None
    superclasse: dict[str, str]
    superclasse_padrao: str | None
    consultas: dict[str, str]
    rotulo: str
    rotulos: dict[str, str]
    gerais: tuple[str, ...]= ()
    descricoes: dict[str, str | list[str]]= field(default_factory=dict)
    negativos: tuple[str, ...]= ()
    limiar_detecao: float= 0.0
    alias: dict[str, str]= field(default_factory=dict)
    combinar_confianca: bool= True


@dataclass(frozen=True)
class Classes:
    categorias: dict[str, Categoria]

    def categoria_de(self, classe: str) -> Categoria | None:
        for categoria in self.categorias.values():
            if classe in categoria.classes or classe in categoria.alias:
                return categoria
        return None


def _ler(path: Path) -> dict:
    if not path.exists():
        raise ErroPipeline(f"Ficheiro de configuração não encontrado: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_municipio(path: Path) -> Municipio:
    dados= _ler(path)
    try:
        bbox= dados["bbox"]
        lon_min, lat_min, lon_max, lat_max= (
            float(bbox[chave]) for chave in ("lon_min", "lat_min", "lon_max", "lat_max")
        )
        nome= str(dados["nome"])
        crs= str(dados["crs_metrico"])
    except (KeyError, TypeError, ValueError) as erro:
        raise ErroPipeline(f"municipio.yaml inválido: {erro!r}") from erro
    if lon_min >= lon_max or lat_min >= lat_max:
        raise ErroPipeline("bbox inválida: os mínimos têm de ser menores que os máximos")
    return Municipio(nome, (lon_min, lat_min, lon_max, lat_max), crs)


def load_classes(path: Path) -> Classes:
    dados= _ler(path)
    categorias= {}
    try:
        for nome, campos in dados["categorias"].items():
            limiar= campos.get("limiar_especifica")
            categorias[nome]= Categoria(
                nome=nome,
                classes=tuple(campos["classes"]),
                raio_dedup_m=float(campos["raio_dedup_m"]),
                altura_m=float(campos["altura_m"]),
                limiar_especifica=None if limiar is None else float(limiar),
                superclasse=dict(campos.get("superclasse", {})),
                superclasse_padrao=campos.get("superclasse_padrao"),
                consultas=dict(campos.get("consultas", {})),
                rotulo=str(campos.get("rotulo", nome)),
                rotulos=dict(campos.get("rotulos", {})),
                gerais=tuple(campos.get("gerais", ())),
                descricoes=dict(campos.get("descricoes", {})),
                negativos=tuple(campos.get("negativos", ())),
                limiar_detecao=float(campos.get("limiar_detecao", 0.0)),
                alias=dict(campos.get("alias", {})),
                combinar_confianca=bool(campos.get("combinar_confianca", True)),
            )
    except (KeyError, TypeError, ValueError, AttributeError) as erro:
        raise ErroPipeline(f"classes.yaml inválido: {erro!r}") from erro
    return Classes(categorias)
