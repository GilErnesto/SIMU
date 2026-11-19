import pytest

from pipeline.ouro import _validar_tela, escolher
from pipeline.ouro_avaliar import caixas_de_ouro, emparelhar, iou, medir, relatorio


def _g(caixa, classe= "stop", estado= "aceite"):
    return {"caixa": caixa, "classe": classe, "estado": estado}


def _p(caixa, classe= "stop", confianca= 0.9):
    return {"caixa": caixa, "classe": classe, "confianca": confianca}


def test_iou_de_caixas_iguais_e_disjuntas():
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0
    assert iou([0, 0, 10, 10], [5, 0, 15, 10]) == pytest.approx(50 / 150)


def test_emparelhar_e_um_para_um_pelas_mais_sobrepostas():
    ouro= [_g([0, 0, 10, 10])]
    previstas= [_p([1, 1, 10, 10]), _p([0, 0, 10, 10])]
    assert emparelhar(previstas, ouro) == [(1, 0)]


def test_emparelhar_ignora_sobreposicao_abaixo_do_limiar():
    assert emparelhar([_p([0, 0, 10, 10])], [_g([8, 8, 20, 20])]) == []


def test_caixas_de_ouro_so_tem_aceites_e_corrigidas_de_imagens_revistas():
    telas= {
        "a": {"revista": True, "caixas": [_g([0, 0, 5, 5]), _g([0, 0, 6, 6], estado= "rejeitado"),
                                          _g([0, 0, 7, 7], estado= "corrigido")]},
        "b": {"revista": False, "caixas": [_g([0, 0, 5, 5])]},
    }
    ouro= caixas_de_ouro(telas)
    assert list(ouro) == ["a"]
    assert [c["caixa"][2] for c in ouro["a"]] == [5, 7]


def test_medir_conta_achadas_falsos_alarmes_e_falhas():
    ouro= {"a": [_g([0, 0, 10, 10]), _g([50, 50, 70, 70], "perigo")]}
    previsoes= {"a": [_p([0, 0, 10, 10]), _p([100, 100, 120, 120], "stop")]}
    m= medir(ouro, previsoes, 0.3)
    assert (m["tp"], m["fp"], m["fn"], m["tipo_certo"]) == (1, 1, 1, 1)
    assert m["precisao"] == 0.5
    assert m["recall"] == 0.5
    assert m["falsos"]["stop"] == 1


def test_medir_respeita_o_limiar_de_confianca():
    ouro= {"a": [_g([0, 0, 10, 10])]}
    previsoes= {"a": [_p([0, 0, 10, 10], confianca= 0.2)]}
    assert medir(ouro, previsoes, 0.3)["tp"] == 0
    assert medir(ouro, previsoes, 0.1)["tp"] == 1


def test_medir_regista_tipo_errado_e_tamanho():
    ouro= {"a": [_g([0, 0, 10, 40], "perigo")]}
    m= medir(ouro, {"a": [_p([0, 0, 10, 40], "stop")]}, 0.3)
    assert m["tp"] == 1
    assert m["tipo_certo"] == 0
    assert m["confusao"][("perigo", "stop")] == 1
    assert m["por_tamanho"]["24-48 px"] == [1, 1]


def test_relatorio_sem_previsoes_nao_falha():
    texto= relatorio({"a": [_g([0, 0, 10, 10])]}, {"a": []}, "teste", 0.3)
    assert "Gold-set results: teste" in texto
    assert "n/a" in texto


def test_escolher_e_estavel_e_respeita_a_quantidade():
    ids= [str(i) for i in range(50)]
    assert escolher(ids, 10, 0) == escolher(list(reversed(ids)), 10, 0)
    assert len(escolher(ids, 10, 0)) == 10
    assert escolher(ids, 10, 0) != escolher(ids, 10, 1)


def test_validar_tela_recusa_caixa_fora_e_estado_invalido():
    atual= {"largura": 100, "altura": 100, "caixas": []}
    base= {"caixa": [0, 0, 10, 10], "categoria": "sinal", "classe": "stop", "estado": "aceite"}
    ok= _validar_tela({"revista": True, "caixas": [base]}, atual)
    assert ok["revista"] is True
    with pytest.raises(ValueError, match="outside"):
        _validar_tela({"caixas": [{**base, "caixa": [0, 0, 200, 10]}]}, atual)
    with pytest.raises(ValueError, match="state"):
        _validar_tela({"caixas": [{**base, "estado": "xpto"}]}, atual)


class _DetetorFalso:
    def __init__(self):
        self.tamanhos= []

    def detect(self, image_id, image):
        from pipeline.models import Detection

        self.tamanhos.append(image.shape[:2])
        return [Detection(image_id, "sinal", "stop", (10.0, 10.0, 50.0, 50.0), 0.9, False)]


def test_ladrilhos_cobrem_a_foto_grande_e_somam_o_desvio():
    import numpy as np

    from pipeline.ouro import detetar_com_ladrilhos

    detetor= _DetetorFalso()
    resultado= detetar_com_ladrilhos(detetor, "img", np.zeros((1536, 2048, 3), np.uint8))
    assert detetor.tamanhos[0] == (1536, 2048)
    assert all(t == (1024, 1024) for t in detetor.tamanhos[1:])
    assert len(detetor.tamanhos) == 1 + 3 * 2
    assert max(d.bbox_xyxy[0] for d in resultado) > 1000


def test_ladrilhos_nao_dividem_imagens_pequenas():
    import numpy as np

    from pipeline.ouro import detetar_com_ladrilhos

    detetor= _DetetorFalso()
    detetar_com_ladrilhos(detetor, "vista", np.zeros((960, 960, 3), np.uint8))
    assert detetor.tamanhos == [(960, 960)]
