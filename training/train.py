import argparse
import shutil
import sys
from pathlib import Path

import yaml

OBRIGATORIOS= ("dados", "modelo", "epocas", "imgsz", "lote", "nome", "destino")


def ler_config(caminho: Path) -> dict:
    config= yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    em_falta= [chave for chave in OBRIGATORIOS if chave not in config]
    if em_falta:
        raise ValueError(f"{caminho}: faltam {', '.join(em_falta)}")
    if not Path(config["dados"]).exists():
        raise FileNotFoundError(f"Dataset não encontrado: {config['dados']}. Correr primeiro o conversor.")
    return config


def treinar(config: dict, retomar: bool= False) -> Path:
    from ultralytics import YOLO

    pasta= Path(config.get("pasta", "data/treino"))
    ultimo= pasta / config["nome"] / "weights" / "last.pt"
    modelo= YOLO(str(ultimo) if retomar and ultimo.exists() else config["modelo"])
    modelo.train(
        data=config["dados"],
        epochs=config["epocas"],
        imgsz=config["imgsz"],
        batch=config["lote"],
        project=str(pasta.resolve()),
        name=config["nome"],
        exist_ok=True,
        resume=retomar and ultimo.exists(),
        seed=config.get("semente", 0),
        workers=config.get("trabalhadores", 4),
        patience=config.get("paciencia", 15),
        time=config.get("tempo"),
        plots=config.get("graficos", True),
        **config.get("aumentos", {}),
    )
    melhor= pasta / config["nome"] / "weights" / "best.pt"
    destino= Path(config["destino"])
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(melhor, destino)
    return destino


def main(argv: list[str] | None= None) -> int:
    parser= argparse.ArgumentParser(prog="python -m training.train")
    parser.add_argument("--config", required=True, help="training/configs/<modelo>.yaml")
    parser.add_argument("--retomar", action="store_true", help="continua a partir do último checkpoint")
    args= parser.parse_args(argv)
    try:
        config= ler_config(Path(args.config))
    except (ValueError, FileNotFoundError) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    destino= treinar(config, args.retomar)
    print(f"Pesos copiados para {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
