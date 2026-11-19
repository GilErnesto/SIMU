import bisect
import itertools
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from pipeline.errors import ErroPipeline
from pipeline.geolocate.triangulate import ALCANCE_MAX_M

ZONA_MAX_GRAUS= 0.02


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
    calibracao: tuple[tuple[float, float], ...]= ()
    alcance_max_m: float= ALCANCE_MAX_M
    seguir_video: bool= False
    tipos_exclusivos: bool= False


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


def _calibracao(campos: dict) -> tuple[tuple[float, float], ...]:
    pares= tuple((float(bruto), float(calibrado)) for bruto, calibrado in campos.get("calibracao", ()))
    brutos= [bruto for bruto, _ in pares]
    if any(not 0 <= valor <= 1 for par in pares for valor in par):
        raise ValueError("calibracao: valores fora de [0, 1]")
    if any(anterior >= seguinte for anterior, seguinte in itertools.pairwise(brutos)):
        raise ValueError("calibracao: valores brutos têm de ser estritamente crescentes")
    return pares


def calibrar_confianca(categoria: Categoria, confianca: float) -> float:
    pares= categoria.calibracao
    if not pares:
        return confianca
    brutos= [bruto for bruto, _ in pares]
    if confianca <= brutos[0]:
        return pares[0][1]
    if confianca >= brutos[-1]:
        return pares[-1][1]
    i= bisect.bisect_right(brutos, confianca)
    (x0, y0), (x1, y1)= pares[i - 1], pares[i]
    return y0 + (y1 - y0) * (confianca - x0) / (x1 - x0)


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


def aplicar_bbox(municipio: Municipio, texto: str | None) -> Municipio:
    if not texto:
        return municipio
    try:
        lon_min, lat_min, lon_max, lat_max= (float(valor) for valor in texto.split(","))
    except ValueError as erro:
        raise ErroPipeline("--bbox deve ser lon_min,lat_min,lon_max,lat_max") from erro
    if not (-180 <= lon_min and lon_max <= 180 and -90 <= lat_min and lat_max <= 90):
        raise ErroPipeline("--bbox fora de limites: a ordem é lon_min,lat_min,lon_max,lat_max")
    if lon_min >= lon_max or lat_min >= lat_max:
        raise ErroPipeline("bbox inválida: os mínimos têm de ser menores que os máximos")
    return replace(municipio, bbox=(lon_min, lat_min, lon_max, lat_max))


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
                calibracao=_calibracao(campos),
                alcance_max_m=float(campos.get("alcance_max_m", ALCANCE_MAX_M)),
                seguir_video=bool(campos.get("seguir_video", False)),
                tipos_exclusivos=bool(campos.get("tipos_exclusivos", False)),
            )
    except (KeyError, TypeError, ValueError, AttributeError) as erro:
        raise ErroPipeline(f"classes.yaml inválido: {erro!r}") from erro
    return Classes(categorias)
