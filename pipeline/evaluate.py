import argparse
import json
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

from pyproj import Transformer

from pipeline.config import load_municipio
from pipeline.errors import ErroPipeline


@dataclass(frozen=True)
class ResultadoClasse:
    classe: str
    verdadeiros: int
    falsos_positivos: int
    falsos_negativos: int
    erro_medio_m: float | None
    erro_mediano_m: float | None

    @property
    def precisao(self) -> float | None:
        total= self.verdadeiros + self.falsos_positivos
        return None if total == 0 else self.verdadeiros / total

    @property
    def recall(self) -> float | None:
        total= self.verdadeiros + self.falsos_negativos
        return None if total == 0 else self.verdadeiros / total


def _pontos(colecao: dict, para_metros: Transformer, ignorar_rejeitados: bool) -> dict[str, list[tuple[float, float]]]:
    por_classe= {}
    for feature in colecao.get("features", []):
        propriedades= feature.get("properties") or {}
        classe= propriedades.get("classe")
        if classe is None:
            raise ErroPipeline("Feature sem a propriedade 'classe'")
        if ignorar_rejeitados and propriedades.get("estado") == "rejeitado":
            continue
        lon, lat= feature["geometry"]["coordinates"][:2]
        por_classe.setdefault(classe, []).append(para_metros.transform(lon, lat))
    return por_classe


def _emparelhar(previstos, referencias, tolerancia_m: float) -> list[float]:
    pares= sorted(
        (math.dist(p, r), i, j)
        for i, p in enumerate(previstos)
        for j, r in enumerate(referencias)
        if math.dist(p, r) <= tolerancia_m
    )
    usados_p= set()
    usados_r= set()
    distancias= []
    for distancia, i, j in pares:
        if i in usados_p or j in usados_r:
            continue
        usados_p.add(i)
        usados_r.add(j)
        distancias.append(distancia)
    return distancias


def evaluate(
    previsto: dict,
    referencia: dict,
    crs_metrico: str,
    tolerancia_m: float,
    ignorar_rejeitados: bool= True,
) -> list[ResultadoClasse]:
    para_metros= Transformer.from_crs("EPSG:4326", crs_metrico, always_xy=True)
    previstos= _pontos(previsto, para_metros, ignorar_rejeitados)
    referencias= _pontos(referencia, para_metros, False)
    resultados= []
    for classe in sorted(set(previstos) | set(referencias)):
        p= previstos.get(classe, [])
        r= referencias.get(classe, [])
        distancias= _emparelhar(p, r, tolerancia_m)
        resultados.append(
            ResultadoClasse(
                classe=classe,
                verdadeiros=len(distancias),
                falsos_positivos=len(p) - len(distancias),
                falsos_negativos=len(r) - len(distancias),
                erro_medio_m=statistics.fmean(distancias) if distancias else None,
                erro_mediano_m=statistics.median(distancias) if distancias else None,
            )
        )
    return resultados


def _formatar(valor: float | None, casas: int, sufixo: str= "") -> str:
    return "n/d" if valor is None else f"{valor:.{casas}f}{sufixo}"


def to_markdown(resultados: list[ResultadoClasse], tolerancia_m: float) -> str:
    linhas= [
        f"Tolerância de emparelhamento: {tolerancia_m:g} m.",
        "",
        "| Classe | Verdadeiros | Falsos positivos | Falsos negativos | Precisão | Recall | Erro médio | Erro mediano |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in resultados:
        linhas.append(
            f"| {r.classe} | {r.verdadeiros} | {r.falsos_positivos} | {r.falsos_negativos} "
            f"| {_formatar(r.precisao, 2)} | {_formatar(r.recall, 2)} "
            f"| {_formatar(r.erro_medio_m, 1, ' m')} | {_formatar(r.erro_mediano_m, 1, ' m')} |"
        )
    return "\n".join(linhas) + "\n"


def _ler(caminho: str) -> dict:
    ficheiro= Path(caminho)
    if not ficheiro.exists():
        raise ErroPipeline(f"Ficheiro não encontrado: {ficheiro}")
    try:
        return json.loads(ficheiro.read_text(encoding="utf-8"))
    except json.JSONDecodeError as erro:
        raise ErroPipeline(f"{ficheiro} não é um GeoJSON válido: {erro}") from erro


def main(argv: list[str] | None= None) -> int:
    parser= argparse.ArgumentParser(prog="python -m pipeline.evaluate")
    parser.add_argument("--municipio", required=True, help="ficheiro municipio.yaml")
    parser.add_argument("--previsto", required=True, help="GeoJSON exportado do catálogo")
    parser.add_argument("--referencia", required=True, help="GeoJSON anotado à mão, com 'classe'")
    parser.add_argument("--tolerancia", type=float, default=15.0, help="metros")
    parser.add_argument("--incluir-rejeitados", action="store_true")
    args= parser.parse_args(argv)
    try:
        municipio= load_municipio(Path(args.municipio))
        resultados= evaluate(
            _ler(args.previsto),
            _ler(args.referencia),
            municipio.crs_metrico,
            args.tolerancia,
            not args.incluir_rejeitados,
        )
    except ErroPipeline as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    print(to_markdown(resultados, args.tolerancia))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
