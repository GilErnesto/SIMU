from argparse import Namespace

from pipeline import run


def test_so_carrega_as_cabecas_que_existem(tmp_path):
    residuos= tmp_path / "res.npz"
    residuos.write_bytes(b"x")
    args= Namespace(cabeca_sinal=str(tmp_path / "nao.npz"), cabeca_iluminacao=None, cabeca_residuos=str(residuos))
    cabecas= run._cabecas(args)
    assert cabecas.get("residuos") == residuos
    assert "sinal" not in cabecas


def test_sem_argumento_usa_o_caminho_por_omissao(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "models").mkdir()
    (tmp_path / run.CABECA_RESIDUOS).write_bytes(b"x")
    # O worker não tem --cabeca-residuos: tem de cair no caminho por omissão.
    assert set(run._cabecas(Namespace())) == {"residuos"}


def test_sem_ficheiros_nao_ha_cabecas(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert run._cabecas(Namespace()) == {}
