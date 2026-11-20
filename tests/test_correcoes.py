from training.correcoes import etiqueta, posicao_do_tecnico

GERAIS= {"luz"}


def test_rejeitado_vira_negativo_na_iluminacao_e_nos_residuos():
    assert etiqueta("rejeitado", "luz", False, "iluminacao", GERAIS) == "nao_luz"
    assert etiqueta("rejeitado", "contentor", False, "residuos", {"contentor"}) == "nao_residuo"
    assert etiqueta("rejeitado", "stop", False, "sinal", set()) is None


def test_negativos_nao_sao_classes_da_categoria():
    # Se fossem, o DuasFases não descartava a deteção quando a cabeça os prevê.
    from pathlib import Path

    from pipeline.config import load_classes
    from training.correcoes import NEGATIVOS

    classes= load_classes(Path("config/classes.yaml"))
    for categoria, negativo in NEGATIVOS.items():
        assert negativo not in classes.categorias[categoria].classes


def test_residuo_validado_usa_o_subtipo():
    assert etiqueta("validado", "ilha_reciclagem", False, "residuos", {"contentor"}) == "ilha_reciclagem"
    assert etiqueta("validado", "contentor", False, "residuos", {"contentor"}) is None


def test_validado_usa_a_classe_do_elemento():
    assert etiqueta("validado", "candeeiro", False, "iluminacao", GERAIS) == "candeeiro"


def test_classe_corrigida_conta_mesmo_corrigido():
    assert etiqueta("corrigido", "candeeiro", True, "iluminacao", GERAIS) == "candeeiro"


def test_corrigido_so_na_posicao_nao_confirma_a_classe():
    assert etiqueta("corrigido", "candeeiro", False, "iluminacao", GERAIS) is None


def test_classe_geral_nao_serve_de_etiqueta():
    assert etiqueta("validado", "luz", False, "iluminacao", GERAIS) is None


def test_auto_nunca_serve():
    assert etiqueta("auto", "candeeiro", False, "iluminacao", GERAIS) is None


def test_posicao_do_tecnico_precisa_de_correcao_de_posicao():
    assert posicao_do_tecnico({"posicao", "estado"}, "corrigido")
    assert not posicao_do_tecnico({"estado"}, "validado")


def test_posicao_de_juntar_ou_de_rejeitado_nao_conta():
    assert not posicao_do_tecnico({"posicao", "juntar"}, "corrigido")
    assert not posicao_do_tecnico({"posicao"}, "rejeitado")
