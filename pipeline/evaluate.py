import argparse
import csv
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


def _pontos(
    colecao: dict, para_metros: Transformer, ignorar_rejeitados: bool, nivel: str= "classe"
) -> dict[str, list[tuple[float, float]]]:
    por_classe= {}
    for feature in colecao.get("features", []):
        propriedades= feature.get("properties") or {}
        classe= propriedades.get(nivel)
        if classe is None:
            raise ErroPipeline(f"Feature sem a propriedade '{nivel}'")
        if ignorar_rejeitados and propriedades.get("estado") == "rejeitado":
            continue
        lon, lat= feature["geometry"]["coordinates"][:2]
        por_classe.setdefault(classe, []).append(para_metros.transform(lon, lat))
    return por_classe


def _pares(previstos, referencias, tolerancia_m: float) -> list[tuple[float, int, int]]:
    candidatos= sorted(
        (math.dist(p, r), i, j)
        for i, p in enumerate(previstos)
        for j, r in enumerate(referencias)
        if math.dist(p, r) <= tolerancia_m
    )
    usados_p= set()
    usados_r= set()
    pares= []
    for distancia, i, j in candidatos:
        if i in usados_p or j in usados_r:
            continue
        usados_p.add(i)
        usados_r.add(j)
        pares.append((distancia, i, j))
    return pares


def _emparelhar(previstos, referencias, tolerancia_m: float) -> list[float]:
    return [distancia for distancia, _, _ in _pares(previstos, referencias, tolerancia_m)]


def exatidao_do_tipo(
    previsto: dict,
    referencia: dict,
    crs_metrico: str,
    tolerancia_m: float,
    categoria: str= "sinal",
    ignorar: tuple[str, ...]= ("outro", "contentor"),
) -> tuple[int, int]:
    para_metros= Transformer.from_crs("EPSG:4326", crs_metrico, always_xy=True)

    def lista(colecao):
        return [
            (para_metros.transform(*f["geometry"]["coordinates"][:2]), f["properties"]["classe"])
            for f in colecao.get("features", [])
            if f["properties"].get("categoria") == categoria
            and f["properties"].get("estado") != "rejeitado"
        ]

    p= lista(previsto)
    r= lista(referencia)
    pares= _pares([x for x, _ in p], [x for x, _ in r], tolerancia_m)
    validos= [(i, j) for _, i, j in pares if r[j][1] not in ignorar]
    return sum(1 for i, j in validos if p[i][1] == r[j][1]), len(validos)


def evaluate(
    previsto: dict,
    referencia: dict,
    crs_metrico: str,
    tolerancia_m: float,
    ignorar_rejeitados: bool= True,
    nivel: str= "classe",
) -> list[ResultadoClasse]:
    para_metros= Transformer.from_crs("EPSG:4326", crs_metrico, always_xy=True)
    previstos= _pontos(previsto, para_metros, ignorar_rejeitados, nivel)
    referencias= _pontos(referencia, para_metros, False, nivel)
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


def linha_do_tipo(certos: int, total: int) -> str:
    percentagem= "n/d" if total == 0 else f"{certos / total:.0%}"
    return f"Tipo de sinal certo nos sinais emparelhados (sem 'outro'): {certos} de {total} ({percentagem}).\n"


def _formatar(valor: float | None, casas: int, sufixo: str= "") -> str:
    return "n/d" if valor is None else f"{valor:.{casas}f}{sufixo}"


def to_markdown(resultados: list[ResultadoClasse], tolerancia_m: float, nivel: str= "classe") -> str:
    linhas= [
        f"Tolerância de emparelhamento: {tolerancia_m:g} m.",
        "",
        f"| {nivel.capitalize()} | Verdadeiros | Falsos positivos | Falsos negativos | Precisão | Recall | Erro médio | Erro mediano |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in resultados:
        linhas.append(
            f"| {r.classe} | {r.verdadeiros} | {r.falsos_positivos} | {r.falsos_negativos} "
            f"| {_formatar(r.precisao, 2)} | {_formatar(r.recall, 2)} "
            f"| {_formatar(r.erro_medio_m, 1, ' m')} | {_formatar(r.erro_mediano_m, 1, ' m')} |"
        )
    return "\n".join(linhas) + "\n"


def cobertos(referencia: dict, imagens: dict, crs_metrico: str, raio_m: float) -> dict:
    para_metros= Transformer.from_crs("EPSG:4326", crs_metrico, always_xy=True)
    origens= [para_metros.transform(*f["geometry"]["coordinates"][:2]) for f in imagens.get("features", [])]
    ficam= [
        feature
        for feature in referencia.get("features", [])
        if any(math.dist(para_metros.transform(*feature["geometry"]["coordinates"][:2]), o) <= raio_m for o in origens)
    ]
    return {**referencia, "features": ficam}


def ler_tabela(texto: str) -> dict:
    linhas= [linha for linha in texto.splitlines() if linha.strip() and not linha.lstrip().startswith("#")]
    try:
        dialeto= csv.Sniffer().sniff(linhas[0], delimiters=",;\t")
    except (csv.Error, IndexError) as erro:
        raise ErroPipeline("Tabela de referência vazia ou sem separador reconhecido") from erro
    leitor= csv.DictReader(linhas, dialect=dialeto)
    campos= {c.strip().lower() for c in leitor.fieldnames or []}
    if not {"lat", "lon"} <= campos or not campos & {"classe", "categoria"}:
        raise ErroPipeline("A tabela precisa das colunas lat, lon e classe (ou categoria)")
    features= []
    for numero, linha in enumerate(leitor, 2):
        valores= {k.strip().lower(): (v or "").strip() for k, v in linha.items() if k}
        try:
            lon= float(valores["lon"].replace(",", "."))
            lat= float(valores["lat"].replace(",", "."))
        except ValueError as erro:
            raise ErroPipeline(f"Linha {numero}: coordenadas inválidas") from erro
        propriedades= {k: valores[k] for k in ("classe", "categoria") if valores.get(k)}
        features.append(
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": propriedades}
        )
    return {"type": "FeatureCollection", "features": features}


def ler(caminho: str) -> dict:
    ficheiro= Path(caminho)
    if not ficheiro.exists():
        raise ErroPipeline(f"Ficheiro não encontrado: {ficheiro}")
    if ficheiro.suffix.lower() in (".csv", ".txt", ".tsv"):
        return ler_tabela(ficheiro.read_text(encoding="utf-8"))
    try:
        return json.loads(ficheiro.read_text(encoding="utf-8"))
    except json.JSONDecodeError as erro:
        raise ErroPipeline(f"{ficheiro} não é um GeoJSON válido: {erro}") from erro


def main(argv: list[str] | None= None) -> int:
    parser= argparse.ArgumentParser(prog="python -m pipeline.evaluate")
    parser.add_argument("--municipio", required=True, help="ficheiro municipio.yaml")
    parser.add_argument("--previsto", required=True, help="GeoJSON exportado do catálogo")
    parser.add_argument("--referencia", required=True, help="GeoJSON ou CSV (lat, lon, classe/categoria)")
    parser.add_argument("--nivel", choices=("classe", "categoria"), default="classe")
    parser.add_argument("--tolerancia", type=float, default=15.0, help="metros")
    parser.add_argument("--incluir-rejeitados", action="store_true")
    parser.add_argument("--cobertura", help="GeoJSON com as posições das imagens: só conta o que está perto delas")
    parser.add_argument("--raio-cobertura", type=float, default=30.0, help="metros")
    args= parser.parse_args(argv)
    try:
        municipio= load_municipio(Path(args.municipio))
        previsto= ler(args.previsto)
        referencia= ler(args.referencia)
        if args.cobertura:
            imagens= ler(args.cobertura)
            previsto= cobertos(previsto, imagens, municipio.crs_metrico, args.raio_cobertura)
            referencia= cobertos(referencia, imagens, municipio.crs_metrico, args.raio_cobertura)
        resultados= evaluate(
            previsto,
            referencia,
            municipio.crs_metrico,
            args.tolerancia,
            not args.incluir_rejeitados,
            args.nivel,
        )
    except ErroPipeline as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    print(to_markdown(resultados, args.tolerancia, args.nivel))
    if args.nivel == "classe":
        print(linha_do_tipo(*exatidao_do_tipo(previsto, referencia, municipio.crs_metrico, args.tolerancia)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
