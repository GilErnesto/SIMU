from training.datasets.sinais_web import classe_ecd, itens_bomcondutor, separar_alt, subtipo


def test_separar_alt_tira_codigo_e_nome():
    assert separar_alt("A1A - Curva &agrave; direita") == ("A1A", "Curva à direita")
    assert separar_alt("Luz Verde") == ("", "Luz Verde")


def test_subtipos_stop_e_limite_de_velocidade():
    assert subtipo("cedencia", "B2") == "stop"
    assert subtipo("proibicao", "C13") == "limite_velocidade"
    assert subtipo("proibicao", "C1") == "proibicao"


def test_sinais_de_obras_iguais_aos_permanentes_contam_como_permanentes():
    assert classe_ecd("TempProbicao", "BT1 (C2)") == "proibicao"
    assert classe_ecd("TempProbicao", "BT8 (C13)") == "limite_velocidade"
    assert classe_ecd("TempProbicao", "BT9 (B5)") == "cedencia"
    assert classe_ecd("TempObrigacao", "CT1 (D1a)") == "obrigacao"
    assert classe_ecd("TempProbicao", "BT7") == "proibicao"
    assert classe_ecd("TempPerigo", "AT1") == "temporaria"


def test_itens_bomcondutor_le_imagens_dos_sinais():
    pagina= (
        '<img src="/assets/images/brand/logo.svg"/>'
        '<img src="/assets/images/content/sinais/B2.png" alt="B2 - Paragem obrigatória" width="100px" />'
    )
    (item,)= itens_bomcondutor(pagina, "sinais-cedencia-passagem", "cedencia")
    assert item["url"] == "https://www.bomcondutor.pt/assets/images/content/sinais/B2.png"
    assert (item["codigo"], item["classe"]) == ("B2", "stop")
