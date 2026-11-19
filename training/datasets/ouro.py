"""Converts reviewed gold-set folders (see `pipeline.ouro`) into a YOLO dataset."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from training.datasets.yolo import escrever_data_yaml, linhas_yolo

NOMES= ["outro", "semaforo", "candeeiro", "contentor"]
FRACAO_VALIDACAO= 0.15


def e_validacao(nome: str) -> bool:
    return int(hashlib.sha1(nome.encode()).hexdigest(), 16) % 100 < FRACAO_VALIDACAO * 100


def converter(pastas: list[Path], saida: Path) -> tuple[int, int]:
    if saida.exists():
        shutil.rmtree(saida)
    imagens= caixas= 0
    for pasta in pastas:
        dados= json.loads((pasta / "ouro.json").read_text(encoding="utf-8"))
        for nome, tela in dados["telas"].items():
            if not tela["revista"]:
                continue
            largura, altura= tela["largura"], tela["altura"]
            itens= [
                (NOMES.index("semaforo" if c["classe"] == "semaforo" else "outro"),
                 c["caixa"][0] / largura, c["caixa"][1] / altura, c["caixa"][2] / largura, c["caixa"][3] / altura)
                for c in tela["caixas"]
                if c["estado"] in ("aceite", "corrigido")
            ]
            divisao= "val" if e_validacao(nome) else "train"
            for sub in ("images", "labels"):
                (saida / sub / divisao).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(pasta / "imagens" / tela["imagem"], saida / "images" / divisao / f"{nome}.jpg")
            (saida / "labels" / divisao / f"{nome}.txt").write_text("\n".join(linhas_yolo(itens)) + "\n", encoding="utf-8")
            imagens+= 1
            caixas+= len(itens)
    escrever_data_yaml(saida, NOMES)
    return imagens, caixas


def main(argv: list[str] | None= None) -> int:
    parser= argparse.ArgumentParser(prog="python -m training.datasets.ouro")
    parser.add_argument("--pastas", nargs="+", required=True)
    parser.add_argument("--saida", default="data/datasets/ouro")
    args= parser.parse_args(argv)
    imagens, caixas= converter([Path(p) for p in args.pastas], Path(args.saida))
    print(f"{imagens} imagens, {caixas} caixas em {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
