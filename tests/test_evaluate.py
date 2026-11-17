import json
from pathlib import Path

import pytest
from pyproj import Transformer

from pipeline.config import load_municipio
from pipeline.errors import ErroPipeline
from pipeline.evaluate import (
    cobertos,
    evaluate,
    exatidao_do_tipo,
    ler_tabela,
    linha_do_tipo,
    main,
    to_markdown,
)

MUNICIPIO= load_municipio(Path(__file__).parents[1] / "config" / "municipio.yaml")
PARA_GRAUS= Transformer.from_crs(MUNICIPIO.crs_metrico, "EPSG:4326", always_xy=True)
PARA_METROS= Transformer.from_crs("EPSG:4326", MUNICIPIO.crs_metrico, always_xy=True)
X0, Y0= PARA_METROS.transform(-8.65, 40.64)


def _feature(dx, dy, classe, estado=None):
    lon, lat= PARA_GRAUS.transform(X0 + dx, Y0 + dy)
    propriedades= {"classe": classe}
    if estado:
        propriedades["estado"]= estado
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": propriedades}


def _colecao(*features):
    return {"type": "FeatureCollection", "features": list(features)}


def _por_classe(resultados):
    return {r.classe: r for r in resultados}


def test_emparelha_dentro_da_tolerancia():
    previsto= _colecao(_feature(3, 4, "stop"))
    referencia= _colecao(_feature(0, 0, "stop"))
    r= _por_classe(evaluate(previsto, referencia, MUNICIPIO.crs_metrico, 10))["stop"]
    assert (r.verdadeiros, r.falsos_positivos, r.falsos_negativos) == (1, 0, 0)
    assert r.erro_medio_m == pytest.approx(5.0, abs=0.05)
    assert r.precisao == 1 and r.recall == 1


def test_fora_da_tolerancia_conta_falso_positivo_e_negativo():
    previsto= _colecao(_feature(50, 0, "stop"))
    referencia= _colecao(_feature(0, 0, "stop"))
    r= _por_classe(evaluate(previsto, referencia, MUNICIPIO.crs_metrico, 10))["stop"]
    assert (r.verdadeiros, r.falsos_positivos, r.falsos_negativos) == (0, 1, 1)
    assert r.erro_medio_m is None


def test_classes_diferentes_nao_se_emparelham():
    previsto= _colecao(_feature(0, 0, "cedencia"))
    referencia= _colecao(_feature(0, 0, "stop"))
    r= _por_classe(evaluate(previsto, referencia, MUNICIPIO.crs_metrico, 10))
    assert r["cedencia"].falsos_positivos == 1
    assert r["stop"].falsos_negativos == 1


def test_emparelhamento_um_para_um():
    previsto= _colecao(_feature(0, 0, "candeeiro"), _feature(1, 0, "candeeiro"))
    referencia= _colecao(_feature(0.5, 0, "candeeiro"))
    r= _por_classe(evaluate(previsto, referencia, MUNICIPIO.crs_metrico, 10))["candeeiro"]
    assert (r.verdadeiros, r.falsos_positivos, r.falsos_negativos) == (1, 1, 0)
    assert r.precisao == 0.5


def test_rejeitados_sao_ignorados_por_omissao():
    previsto= _colecao(_feature(0, 0, "stop", "rejeitado"))
    referencia= _colecao(_feature(0, 0, "stop"))
    r= _por_classe(evaluate(previsto, referencia, MUNICIPIO.crs_metrico, 10))["stop"]
    assert (r.verdadeiros, r.falsos_negativos) == (0, 1)
    incluidos= _por_classe(evaluate(previsto, referencia, MUNICIPIO.crs_metrico, 10, False))["stop"]
    assert incluidos.verdadeiros == 1


def test_markdown_tem_cabecalho_e_linha_por_classe():
    texto= to_markdown(evaluate(_colecao(_feature(0, 0, "stop")), _colecao(), MUNICIPIO.crs_metrico, 10), 10)
    assert "| Classe |" in texto
    assert "| stop | 0 | 1 | 0 | 0.00 | n/d | n/d | n/d |" in texto


def test_cli_ficheiro_em_falta(capsys):
    codigo= main(["--municipio", "config/municipio.yaml", "--previsto", "nao_existe.geojson", "--referencia", "x.geojson"])
    assert codigo == 1
    assert "não encontrado" in capsys.readouterr().err


def test_cli_ponta_a_ponta(tmp_path, capsys):
    previsto= tmp_path / "p.geojson"
    referencia= tmp_path / "r.geojson"
    previsto.write_text(json.dumps(_colecao(_feature(2, 0, "stop"))))
    referencia.write_text(json.dumps(_colecao(_feature(0, 0, "stop"))))
    codigo= main(
        [
            "--municipio",
            str(Path(__file__).parents[1] / "config" / "municipio.yaml"),
            "--previsto",
            str(previsto),
            "--referencia",
            str(referencia),
            "--tolerancia",
            "5",
        ]
    )
    assert codigo == 0
    assert "| stop | 1 | 0 | 0 | 1.00 | 1.00 |" in capsys.readouterr().out


def _com(feature, **propriedades):
    return {**feature, "properties": propriedades}


def test_nivel_categoria_ignora_a_classe():
    previsto= _colecao(_com(_feature(0, 0, "x"), classe="proibicao", categoria="sinal"))
    referencia= _colecao(_com(_feature(3, 0, "x"), classe="perigo", categoria="sinal"))
    por_classe= _por_classe(evaluate(previsto, referencia, MUNICIPIO.crs_metrico, 15, nivel="classe"))
    por_categoria= _por_classe(evaluate(previsto, referencia, MUNICIPIO.crs_metrico, 15, nivel="categoria"))
    assert por_classe["proibicao"].verdadeiros == 0
    assert por_categoria["sinal"].verdadeiros == 1


def _sinal(dx, classe, **extra):
    return _com(_feature(dx, 0, classe), classe=classe, categoria="sinal", **extra)


def test_exatidao_do_tipo_ignora_genericos_e_rejeitados():
    previsto= _colecao(
        _sinal(0, "stop"),
        _sinal(30, "cedencia"),
        _sinal(60, "perigo"),
        _sinal(90, "stop", estado="rejeitado"),
        _sinal(120, "stop"),
    )
    referencia= _colecao(
        _sinal(1, "stop"),
        _sinal(31, "perigo"),
        _sinal(61, "outro"),
        _sinal(91, "stop"),
        _sinal(500, "stop"),
    )
    assert exatidao_do_tipo(previsto, referencia, MUNICIPIO.crs_metrico, 5) == (1, 2)


def test_exatidao_do_tipo_sem_categoria_nao_conta():
    assert exatidao_do_tipo(_colecao(_feature(0, 0, "stop")), _colecao(_feature(1, 0, "stop")), MUNICIPIO.crs_metrico, 5) == (0, 0)
    assert "n/d" in linha_do_tipo(0, 0)
    assert "1 de 4 (25%)" in linha_do_tipo(1, 4)


def test_tabela_com_ponto_e_virgula_e_virgula_decimal():
    colecao= ler_tabela("# anotado na rua\nlat;lon;classe\n40,6301;-8,6600;candeeiro\n40.6302;-8.6601;stop\n")
    assert [f["properties"]["classe"] for f in colecao["features"]] == ["candeeiro", "stop"]
    assert colecao["features"][0]["geometry"]["coordinates"] == [-8.66, 40.6301]


def test_tabela_sem_colunas_obrigatorias():
    with pytest.raises(ErroPipeline, match="lat, lon"):
        ler_tabela("x,y,classe\n1,2,stop\n")


def test_tabela_com_coordenada_invalida():
    with pytest.raises(ErroPipeline, match="Linha 2"):
        ler_tabela("lat,lon,categoria\nabc,-8.66,sinal\n")


def test_cobertura_tira_referencias_longe_das_imagens():
    referencia= _colecao(_feature(10, 0, "stop"), _feature(500, 0, "stop"))
    imagens= _colecao(_feature(0, 0, "imagem"))
    assert len(cobertos(referencia, imagens, MUNICIPIO.crs_metrico, 30)["features"]) == 1


def test_cli_le_csv_e_cobertura(tmp_path, capsys):
    lon, lat= PARA_GRAUS.transform(X0, Y0)
    (tmp_path / "ref.csv").write_text(f"lat,lon,classe\n{lat},{lon},stop\n{lat + 0.01},{lon},stop\n")
    (tmp_path / "prev.geojson").write_text(json.dumps(_colecao(_feature(2, 0, "stop"))))
    (tmp_path / "imagens.geojson").write_text(json.dumps(_colecao(_feature(0, 0, "imagem"))))
    codigo= main(
        [
            "--municipio",
            str(Path(__file__).parents[1] / "config" / "municipio.yaml"),
            "--previsto",
            str(tmp_path / "prev.geojson"),
            "--referencia",
            str(tmp_path / "ref.csv"),
            "--cobertura",
            str(tmp_path / "imagens.geojson"),
        ]
    )
    assert codigo == 0
    assert "| stop | 1 | 0 | 0 |" in capsys.readouterr().out
