import json
from collections import Counter

import cv2
import numpy as np
import pytest

from pipeline.detect.panorama import to_panorama
from training import rotulos_para_yolo as exportador


def escrever_lote(base, lote, imagens):
    (base / lote).mkdir(parents=True)
    (base / "rotulos").mkdir(exist_ok=True)
    (base / "imagens").mkdir(exist_ok=True)
    deteccoes= []
    rotulos= []
    for id_fonte, camera, caixas, extra in imagens:
        cv2.imwrite(str(base / "imagens" / f"mapillary_{id_fonte}.jpg"), np.full((400, 800, 3), 120, np.uint8))
        deteccoes.append(
            json.dumps({"imagem": {"id_fonte": id_fonte}, "deteccoes": extra})
        )
        rotulos.append(
            json.dumps({"id": id_fonte, "camera_type": camera, "lat": 40.6, "lon": -8.6, "caixas": caixas})
        )
    (base / lote / "deteccoes.jsonl").write_text("\n".join(deteccoes), encoding="utf-8")
    (base / "rotulos" / f"{lote}.jsonl").write_text("\n".join(rotulos), encoding="utf-8")


def caixa(classe, bbox=(100, 50, 160, 300), origem="modelo"):
    return {"bbox": list(bbox), "classe": classe, "origem": origem}


@pytest.fixture
def base(tmp_path):
    sinal= {"category": "sinal", "class_name": "stop", "bbox_xyxy": [10, 10, 60, 60], "confidence": 0.9}
    fraco= {"category": "sinal", "class_name": "stop", "bbox_xyxy": [200, 10, 260, 60], "confidence": 0.3}
    contentor= {"category": "residuos", "class_name": "contentor", "bbox_xyxy": [300, 200, 380, 300], "confidence": 0.8}
    escrever_lote(
        tmp_path,
        "zona",
        [
            ("1", "perspective", [caixa("poste_luz"), caixa("nao_luz", (400, 50, 460, 300)), caixa("candeeiro", (600, 50, 640, 200), "manual")], [sinal, fraco, contentor]),
            ("2", "spherical", [caixa("poste_luz", (100, 170, 130, 230))], []),
            ("3", "perspective", [], []),
        ],
    )
    return tmp_path


def test_exporta_yolo_so_perspetiva_com_pseudo_rotulos(base, tmp_path):
    saida= tmp_path / "saida"
    contagem= exportador.exportar(base, ["zona"], {"zona"}, saida)
    assert contagem["yolo_val"] == 2
    assert contagem["panoramas"] == 1
    assert contagem["luzes_em_vistas_val"] >= 1
    assert list((saida / "labels" / "val").glob("zona_2_v*.txt"))
    linhas= (saida / "labels" / "val" / "zona_1.txt").read_text().split("\n")
    classes= sorted(int(l.split()[0]) for l in linhas if l)
    assert classes == [0, 2, 2, 3]
    assert (saida / "labels" / "val" / "zona_3.txt").read_text().strip() == ""
    assert not (saida / "labels" / "val" / "zona_2.txt").exists()


def test_recortes_por_classe_incluem_panoramas(base, tmp_path):
    saida= tmp_path / "saida"
    exportador.exportar(base, ["zona"], {"zona"}, saida)
    assert len(list((saida / "recortes" / "val" / "poste_luz").glob("*.jpg"))) == 2
    assert len(list((saida / "recortes" / "val" / "nao_luz").glob("*.jpg"))) == 1
    assert len(list((saida / "recortes" / "val" / "candeeiro").glob("*.jpg"))) == 1


def test_lote_nao_reservado_divide_por_troco(base, tmp_path):
    saida= tmp_path / "saida"
    contagem= exportador.exportar(base, ["zona"], set(), saida)
    divisoes= {k.split("_")[1] for k in contagem if k.startswith("yolo_") and not k.startswith("yolo_vista")}
    assert len(divisoes) == 1


def test_divisao_do_mesmo_troco_e_estavel():
    a= {"id": "1", "lat": 40.62931, "lon": -8.64801}
    b= {"id": "2", "lat": 40.62934, "lon": -8.64798}
    assert exportador.divisao_de(a, False) == exportador.divisao_de(b, False)


def test_divisao_por_imagem_separa_imagens_do_mesmo_troco():
    registos= [{"id": str(i), "lat": 40.62931, "lon": -8.64801} for i in range(60)]
    por_troco= {exportador.divisao_de(r, False) for r in registos}
    por_imagem= {exportador.divisao_de(r, False, True) for r in registos}
    assert len(por_troco) == 1
    assert por_imagem == {"train", "val"}


def test_caixa_na_vista_inverte_to_panorama():
    largura, altura, yaw= 4096, 2048, 120.0
    original= (400.0, 300.0, 460.0, 600.0)
    na_panorama= to_panorama(original, yaw, largura, altura)
    volta= exportador.caixa_na_vista(na_panorama, yaw, largura, altura)
    assert volta is not None
    assert all(abs(a - b) < 4 for a, b in zip(volta, original))


def test_caixa_atras_da_vista_e_ignorada():
    assert exportador.caixa_na_vista((100.0, 900.0, 140.0, 1000.0), 0.0, 4096, 2048) is None


def test_limite_usa_so_as_primeiras_imagens(base, tmp_path):
    contagem= exportador.exportar(base, ["zona"], {"zona"}, tmp_path / "saida", {"zona": 1})
    assert contagem["imagem_fora_do_limite"] == 2
    assert contagem["yolo_val"] == 1


def test_lote_de_residuos_usa_caixas_manuais_e_ignora_pseudo_de_residuos(tmp_path):
    luz= {"category": "iluminacao", "class_name": "luz", "bbox_xyxy": [500, 50, 530, 300], "confidence": 0.9}
    contentor= {"category": "residuos", "class_name": "contentor", "bbox_xyxy": [300, 200, 380, 300], "confidence": 0.8}
    sinal= {"category": "sinal", "class_name": "stop", "bbox_xyxy": [10, 10, 60, 60], "confidence": 0.9}
    escrever_lote(
        tmp_path,
        "res",
        [("1", "perspective", [caixa("ilha_reciclagem", (100, 200, 200, 300)), caixa("nao_residuo", (300, 200, 380, 300))], [luz, contentor, sinal])],
    )
    rotulos= tmp_path / "rotulos" / "res.jsonl"
    registo= json.loads(rotulos.read_text(encoding="utf-8"))
    registo["categoria"]= "residuos"
    rotulos.write_text(json.dumps(registo), encoding="utf-8")

    saida= tmp_path / "saida"
    exportador.exportar(tmp_path, ["res"], {"res"}, saida)
    linhas= (saida / "labels" / "val" / "res_1.txt").read_text().split("\n")
    classes= sorted(int(l.split()[0]) for l in linhas if l)
    # outro (sinal), candeeiro (luz por pseudo-rótulo), contentor (só a ilha manual: o rejeitado não volta)
    assert classes == [exportador.NOMES.index("outro"), exportador.CLASSE_LUZ, exportador.CLASSE_CONTENTOR]
    assert len(list((saida / "recortes" / "val" / "ilha_reciclagem").glob("*.jpg"))) == 1
    assert len(list((saida / "recortes" / "val" / "nao_residuo").glob("*.jpg"))) == 1


def test_residuo_outro_conta_como_contentor_mas_nao_gera_recorte_de_tipo(tmp_path):
    imagem= np.full((300, 400, 3), 120, np.uint8)
    registo= {"caixas": [{"bbox": [100, 100, 200, 200], "classe": "residuo_outro"}]}
    exportador.exportar_recortes(imagem, registo, "l", "1", "train", tmp_path, Counter())
    assert not (tmp_path / "recortes").exists()
    assert exportador.MANUAIS_YOLO["residuo_outro"] == exportador.CLASSE_CONTENTOR


def test_rotulos_sem_categoria_sao_de_luzes():
    registo= {"caixas": [caixa("poste_luz")]}
    pseudo= [("iluminacao", exportador.CLASSE_LUZ, [1, 1, 5, 5]), ("residuos", exportador.CLASSE_CONTENTOR, [9, 9, 20, 20])]
    assert exportador.caixas_da_imagem(registo, pseudo) == [
        (exportador.CLASSE_LUZ, [100, 50, 160, 300]),
        (exportador.CLASSE_CONTENTOR, [9, 9, 20, 20]),
    ]
