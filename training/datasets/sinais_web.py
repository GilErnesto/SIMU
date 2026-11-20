"""Collects reference images of Portuguese road signs, with their code and name, into a dataset.

Sources (each image keeps its source page and URL in `manifesto.jsonl`):
- ecdinamica.pt/sinalizacoes (JSON files the page loads: /assets/jsons/<Categoria>.json)
- bomcondutor.pt/biblioteca (one page per category, code and name in the image `alt`)

Only categories that exist in config/classes.yaml are kept. Sinais do agente, mensagem variável,
marcas rodoviárias and the loose symbols (I-VI) are left out.
"""

import argparse
import html
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote, urljoin

import cv2
import numpy as np
import requests

ECD= "https://ecdinamica.pt"
BC= "https://www.bomcondutor.pt"
AGENTE= "SIMU-dataset/0.1 (hackathon research)"
PAUSA_S= 0.2
TIMEOUT_S= 30

# ecdinamica.pt JSON file -> project class
ECD_FICHEIROS= {
    "Perigo": "perigo",
    "Cedencia": "cedencia",
    "Proibicao": "proibicao",
    "Obrigacao": "obrigacao",
    "Prescricao": "prescricao",
    "Informacao": "informacao",
    "PreSinalizacao": "pre_sinalizacao",
    "Direcao": "direcao",
    "Confirmacao": "confirmacao",
    "Localidades": "localidades",
    "Complementares": "complementares",
    "PaineisAdicionais": "painel_adicional",
    "Turistico": "turistico",
    "TempCirculacao": "temporaria",
    "TempDesvio": "temporaria",
    "TempObrigacao": "temporaria",
    "TempPerigo": "temporaria",
    "TempProbicao": "temporaria",
    "TempVariados": "temporaria",
    "Luminoso": "semaforo",
}
# bomcondutor.pt library page -> project class
BC_PAGINAS= {
    "sinais-perigo": "perigo",
    "sinais-cedencia-passagem": "cedencia",
    "sinais-proibicao": "proibicao",
    "sinais-obrigacao": "obrigacao",
    "sinais-prescricao-especifica": "prescricao",
    "sinais-informacao": "informacao",
    "sinais-pre-sinalizacao": "pre_sinalizacao",
    "sinais-direcao": "direcao",
    "sinais-confirmacao": "confirmacao",
    "sinais-localidades": "localidades",
    "sinais-complementares": "complementares",
    "paineis-adicionais": "painel_adicional",
    "sinais-turistico-cultural": "turistico",
    "sinalizacao-temporaria": "temporaria",
    "sinalizacao-luminosa": "semaforo",
}
IMG_BC= re.compile(r'<img[^>]*src="(/assets/images/content/sinais/[^"]+)"[^>]*alt="([^"]*)"', re.IGNORECASE)


def subtipo(classe: str, codigo: str) -> str:
    """STOP (B2) and speed limits (C13) are subtypes the project keeps apart."""
    codigo= codigo.strip().upper()
    if classe == "cedencia" and codigo == "B2":
        return "stop"
    if classe == "proibicao" and re.fullmatch(r"C13[A-Z]?", codigo):
        return "limite_velocidade"
    return classe


LETRAS= {"A": "perigo", "B": "cedencia", "C": "proibicao", "D": "obrigacao", "H": "informacao"}
# Works signs that look exactly like the permanent ones: classed as the permanent sign, not as temporária.
TEMPORARIOS_IGUAIS= {"TempProbicao": "proibicao", "TempObrigacao": "obrigacao"}


def classe_ecd(ficheiro: str, codigo: str) -> str:
    """'BT1 (C2)' is the works version of C2, which looks the same: it counts as proibição."""
    classe= ECD_FICHEIROS[ficheiro]
    permanente= re.search(r"\(([A-Z])(\d+[a-z]?)\)", codigo)
    if classe == "temporaria" and permanente and permanente.group(1) in LETRAS:
        return subtipo(LETRAS[permanente.group(1)], permanente.group(1) + permanente.group(2))
    if ficheiro in TEMPORARIOS_IGUAIS:
        return TEMPORARIOS_IGUAIS[ficheiro]
    return subtipo(classe, codigo)


def separar_alt(alt: str) -> tuple[str, str]:
    """'A1A - Curva à direita' -> ('A1A', 'Curva à direita')."""
    codigo, _, nome= html.unescape(alt).partition(" - ")
    return (codigo.strip(), nome.strip()) if nome else ("", codigo.strip())


def itens_bomcondutor(pagina_html: str, pagina: str, classe: str) -> list[dict]:
    itens= []
    for src, alt in IMG_BC.findall(pagina_html):
        codigo, nome= separar_alt(alt)
        itens.append({
            "fonte": "bomcondutor.pt",
            "pagina": f"{BC}/biblioteca/{pagina}",
            "url": urljoin(BC, src),
            "codigo": codigo or Path(src).stem,
            "nome": nome,
            "classe": subtipo(classe, codigo or Path(src).stem),
        })
    return itens


def itens_ecdinamica(dados: dict, ficheiro: str) -> list[dict]:
    return [
        {
            "fonte": "ecdinamica.pt",
            "pagina": f"{ECD}/sinalizacoes",
            "url": urljoin(ECD, quote(item["src"], safe="/")),
            "codigo": str(item.get("code", "")).strip(),
            "nome": str(item.get("name", "")).strip(),
            "classe": classe_ecd(ficheiro, str(item.get("code", ""))),
            "json": f"{ECD}/assets/jsons/{ficheiro}.json",
        }
        for item in dados.get("items", [])
        if item.get("src")
    ]


def _obter(sessao: requests.Session, url: str) -> requests.Response:
    resposta= sessao.get(url, timeout=TIMEOUT_S)
    resposta.raise_for_status()
    time.sleep(PAUSA_S)
    return resposta


def _texto(conteudo: bytes) -> str:
    """Some of the JSON files are Windows-1252, not UTF-8."""
    try:
        return conteudo.decode("utf-8")
    except UnicodeDecodeError:
        return conteudo.decode("cp1252")


def listar(sessao: requests.Session, saida=sys.stderr) -> list[dict]:
    itens= []
    for ficheiro in ECD_FICHEIROS:
        try:
            dados= json.loads(_texto(_obter(sessao, f"{ECD}/assets/jsons/{quote(ficheiro)}.json").content))
        except (requests.RequestException, ValueError) as erro:
            print(f"Aviso: ecdinamica {ficheiro}: {erro}", file=saida)
            continue
        itens+= itens_ecdinamica(dados, ficheiro)
    for pagina, classe in BC_PAGINAS.items():
        try:
            texto= _obter(sessao, f"{BC}/biblioteca/{pagina}").text
        except requests.RequestException as erro:
            print(f"Aviso: bomcondutor {pagina}: {erro}", file=saida)
            continue
        itens+= itens_bomcondutor(texto, pagina, classe)
    return itens


def _nome_ficheiro(item: dict, extensao: str) -> str:
    base= re.sub(r"[^A-Za-z0-9_-]+", "_", item["codigo"] or "sem_codigo").strip("_")
    prefixo= "ecd" if item["fonte"].startswith("ecd") else "bc"
    return f"{prefixo}_{base}{extensao}"


def descarregar(itens: list[dict], saida: Path, sessao: requests.Session, log=sys.stderr) -> list[dict]:
    guardados= []
    for n, item in enumerate(itens, 1):
        extensao= Path(item["url"].split("?")[0]).suffix.lower() or ".png"
        destino= saida / "imagens" / item["classe"] / _nome_ficheiro(item, extensao)
        if not destino.exists():
            try:
                conteudo= _obter(sessao, item["url"]).content
            except requests.RequestException as erro:
                print(f"Aviso: {item['url']}: {erro}", file=log)
                continue
            if extensao != ".svg" and cv2.imdecode(np.frombuffer(conteudo, np.uint8), cv2.IMREAD_UNCHANGED) is None:
                print(f"Aviso: não é uma imagem: {item['url']}", file=log)
                continue
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(conteudo)
        guardados.append({**item, "ficheiro": str(destino.relative_to(saida)).replace("\\", "/")})
        if n % 50 == 0:
            print(f"[{n}/{len(itens)}]", file=log, flush=True)
    return guardados


def main(argv: list[str] | None= None) -> int:
    parser= argparse.ArgumentParser(prog="python -m training.datasets.sinais_web")
    parser.add_argument("--saida", default="data/datasets/sinais_web")
    args= parser.parse_args(argv)
    saida= Path(args.saida)
    sessao= requests.Session()
    sessao.headers["User-Agent"]= AGENTE
    itens= listar(sessao)
    guardados= descarregar(itens, saida, sessao)
    saida.mkdir(parents=True, exist_ok=True)
    with (saida / "manifesto.jsonl").open("w", encoding="utf-8") as destino:
        for item in guardados:
            destino.write(json.dumps(item, ensure_ascii=False) + "\n")
    contagem= {}
    for item in guardados:
        contagem[item["classe"]]= contagem.get(item["classe"], 0) + 1
    print(json.dumps(dict(sorted(contagem.items())), ensure_ascii=False))
    print(f"{len(guardados)} imagens em {saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
