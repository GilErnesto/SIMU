from pathlib import Path

import cv2
import numpy as np
import yaml

QUALIDADE_JPEG= 90
LADO_MINIMO_CAIXA= 0.002


def reduzir(imagem: np.ndarray, lado: int) -> np.ndarray:
    altura, largura= imagem.shape[:2]
    escala= lado / max(altura, largura)
    if escala >= 1:
        return imagem
    return cv2.resize(imagem, (round(largura * escala), round(altura * escala)), interpolation=cv2.INTER_AREA)


def linhas_yolo(caixas: list[tuple[int, float, float, float, float]]) -> list[str]:
    linhas= []
    for indice, x0, y0, x1, y1 in caixas:
        x0, x1= sorted((min(max(x0, 0.0), 1.0), min(max(x1, 0.0), 1.0)))
        y0, y1= sorted((min(max(y0, 0.0), 1.0), min(max(y1, 0.0), 1.0)))
        if x1 - x0 < LADO_MINIMO_CAIXA or y1 - y0 < LADO_MINIMO_CAIXA:
            continue
        linhas.append(f"{indice} {(x0 + x1) / 2:.6f} {(y0 + y1) / 2:.6f} {x1 - x0:.6f} {y1 - y0:.6f}")
    return linhas


def guardar_exemplo(
    saida: Path,
    divisao: str,
    nome: str,
    imagem: np.ndarray,
    caixas: list[tuple[int, float, float, float, float]],
    anonimizador,
    lado: int,
    lado_anonimizar: int | None= None,
) -> None:
    pasta_imagens= saida / "images" / divisao
    pasta_rotulos= saida / "labels" / divisao
    pasta_imagens.mkdir(parents=True, exist_ok=True)
    pasta_rotulos.mkdir(parents=True, exist_ok=True)
    anonima= reduzir(anonimizador(reduzir(imagem, lado_anonimizar or lado)), lado)
    if not cv2.imwrite(str(pasta_imagens / f"{nome}.jpg"), anonima, [cv2.IMWRITE_JPEG_QUALITY, QUALIDADE_JPEG]):
        raise OSError(f"Não foi possível gravar {nome}.jpg")
    (pasta_rotulos / f"{nome}.txt").write_text("\n".join(linhas_yolo(caixas)) + "\n", encoding="utf-8")


def escrever_data_yaml(saida: Path, nomes: list[str]) -> Path:
    destino= saida / "data.yaml"
    conteudo= {
        "path": str(saida.resolve()),
        "train": "images/train",
        "val": "images/val",
        "names": dict(enumerate(nomes)),
    }
    destino.write_text(yaml.safe_dump(conteudo, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return destino


def escrever_data_yaml_conjunto(destino: Path, pastas: list[Path], nomes: list[str]) -> Path:
    conteudo= {
        "train": [str((p / "images" / "train").resolve()) for p in pastas],
        "val": [str((p / "images" / "val").resolve()) for p in pastas],
        "names": dict(enumerate(nomes)),
    }
    destino.write_text(yaml.safe_dump(conteudo, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return destino
