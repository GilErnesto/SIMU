import pytest

from pipeline.detect.conjunto import Conjunto, juntar
from pipeline.models import Detection
from pipeline.run import lista_de_pesos


def _d(caixa, conf, classe= "outro", categoria= "sinal"):
    return Detection("img", categoria, classe, caixa, conf, False)


def test_caixa_vista_por_todos_mantem_a_confianca_media():
    (unica,)= juntar([[_d((0, 0, 10, 10), 0.8)], [_d((1, 0, 11, 10), 0.6, "stop")]])
    assert unica.confidence == pytest.approx(0.7)
    assert unica.class_name == "outro"
    assert unica.bbox_xyxy == pytest.approx((0.5, 0, 10.5, 10))


def test_caixa_vista_so_por_um_perde_metade_da_confianca():
    resultado= juntar([[_d((0, 0, 10, 10), 0.8)], [_d((50, 50, 60, 60), 0.6)]])
    assert sorted(d.confidence for d in resultado) == pytest.approx([0.3, 0.4])


def test_nao_junta_categorias_diferentes_nem_caixas_do_mesmo_membro():
    resultado= juntar([[_d((0, 0, 10, 10), 0.8), _d((0, 0, 10, 10), 0.7, categoria="residuos")]])
    assert len(resultado) == 2
    assert len(juntar([[_d((0, 0, 10, 10), 0.8), _d((1, 0, 11, 10), 0.7)]])) == 2


class _Fixo:
    def __init__(self, deteccoes):
        self.deteccoes= deteccoes

    def detect(self, image_id, image):
        return self.deteccoes


def test_conjunto_chama_todos_os_membros():
    conjunto= Conjunto([_Fixo([_d((0, 0, 10, 10), 0.9)]), _Fixo([_d((0, 0, 10, 10), 0.5)])])
    (unica,)= conjunto.detect("img", None)
    assert unica.confidence == pytest.approx(0.7)


def test_lista_de_pesos_aceita_um_ou_varios():
    assert [p.name for p in lista_de_pesos("models/a.pt")] == ["a.pt"]
    assert [p.name for p in lista_de_pesos("models/a.pt, models/b.pt")] == ["a.pt", "b.pt"]


def test_pesos_padrao_so_inclui_o_segundo_detetor_se_existir(tmp_path, monkeypatch):
    from pipeline import run

    principal, extra= tmp_path / "a.pt", tmp_path / "b.pt"
    monkeypatch.setattr(run, "PESOS_PRINCIPAIS", principal)
    monkeypatch.setattr(run, "PESOS_EXTRA", (extra,))
    assert run.pesos_padrao() == str(principal)
    extra.write_bytes(b"x")
    assert run.pesos_padrao() == f"{principal},{extra}"
