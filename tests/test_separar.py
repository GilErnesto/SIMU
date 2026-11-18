import math
from types import SimpleNamespace

from pipeline.geolocate.separar import separar_mesma_imagem

POSTE_A= (-5.0, 30.0)
POSTE_B= (8.0, 42.0)


def rumo(origem, ponto):
    return math.degrees(math.atan2(ponto[0] - origem[0], ponto[1] - origem[1]))


def obs(imagem, origem, ponto, caixa, classe="luz", confianca=0.8):
    return SimpleNamespace(
        image=SimpleNamespace(id=imagem),
        detection=SimpleNamespace(class_name=classe, confidence=confianca, bbox_xyxy=caixa),
        bearing=rumo(origem, ponto),
    )


def cena():
    origens_por_imagem= {"a": (0.0, 0.0), "b": (20.0, 0.0), "c": (-15.0, 5.0)}
    pontos= {"p1": POSTE_A, "p2": POSTE_B}
    observacoes= []
    origens= []
    alvo= []
    for k, (imagem, origem) in enumerate(origens_por_imagem.items()):
        for n, (nome, ponto) in enumerate(pontos.items()):
            observacoes.append(obs(imagem, origem, ponto, (100 + 300 * n, 50, 140 + 300 * n, 300)))
            origens.append(origem)
            alvo.append(ponto)
    return observacoes, origens, alvo


def monocular_com_erro(observacao, origem, altura_m):
    for ponto in (POSTE_A, POSTE_B):
        if abs(rumo(origem, ponto) - observacao.bearing) < 1e-6:
            return (ponto[0] + 1.5, ponto[1] - 2.0)
    return None


def membros_fundidos(n):
    return [((0.0, 35.0), set(range(n)), "monocular")]


def test_dois_postes_da_mesma_foto_ficam_em_elementos_diferentes():
    observacoes, origens, _= cena()
    grupos= separar_mesma_imagem(membros_fundidos(len(observacoes)), observacoes, origens, {"luz"}, monocular_com_erro, 6.0)
    assert len(grupos) == 2
    for grupo in grupos:
        indices= grupo[0][1]
        imagens= [observacoes[i].image.id for i in indices]
        assert sorted(imagens) == ["a", "b", "c"]
    centros= sorted(g[0][0] for g in grupos)
    assert math.dist(centros[0], POSTE_A) < 2.0
    assert math.dist(centros[1], POSTE_B) < 2.0
    assert all(g[0][2] == "triangulacao" for g in grupos)


def test_caixas_sobrepostas_da_mesma_foto_sao_o_mesmo_poste():
    observacoes= [
        obs("a", (0.0, 0.0), POSTE_A, (100, 50, 140, 300)),
        obs("a", (0.0, 0.0), POSTE_A, (105, 60, 145, 310)),
        obs("b", (20.0, 0.0), POSTE_A, (100, 50, 140, 300)),
    ]
    origens= [(0.0, 0.0), (0.0, 0.0), (20.0, 0.0)]
    membros= membros_fundidos(3)
    grupos= separar_mesma_imagem(membros, observacoes, origens, {"luz"}, monocular_com_erro, 6.0)
    assert grupos == [membros]


def test_classes_diferentes_na_mesma_foto_nao_se_separam():
    observacoes= [
        obs("a", (0.0, 0.0), POSTE_A, (100, 50, 140, 300), classe="stop"),
        obs("a", (0.0, 0.0), POSTE_B, (400, 50, 440, 300), classe="proibicao"),
        obs("b", (20.0, 0.0), POSTE_A, (100, 50, 140, 300), classe="stop"),
    ]
    origens= [(0.0, 0.0), (0.0, 0.0), (20.0, 0.0)]
    membros= membros_fundidos(3)
    assert separar_mesma_imagem(membros, observacoes, origens, set(), monocular_com_erro, 1.2) == [membros]


def test_caixa_extra_sem_par_vira_novo_elemento():
    observacoes, origens, _= cena()
    observacoes.append(obs("d", (0.0, 0.0), (30.0, 10.0), (700, 50, 740, 300)))
    origens.append((0.0, 0.0))
    observacoes[-1].bearing= 70.0
    grupos= separar_mesma_imagem(membros_fundidos(len(observacoes)), observacoes, origens, {"luz"}, monocular_com_erro, 6.0)
    assert len(grupos) in (2, 3)
    assert max(len(g[0][1]) for g in grupos) >= 3


def test_sem_conflito_devolve_o_grupo_original():
    observacoes= [
        obs("a", (0.0, 0.0), POSTE_A, (100, 50, 140, 300)),
        obs("b", (20.0, 0.0), POSTE_A, (100, 50, 140, 300)),
    ]
    origens= [(0.0, 0.0), (20.0, 0.0)]
    membros= membros_fundidos(2)
    assert separar_mesma_imagem(membros, observacoes, origens, {"luz"}, monocular_com_erro, 6.0) == [membros]


def obs_simples(imagem):
    return SimpleNamespace(image=SimpleNamespace(id=imagem))


def grupo(ponto, indices):
    return [(ponto, set(indices), "monocular")]


def test_funde_elementos_proximos_sem_fotos_em_comum():
    from pipeline.geolocate.separar import fundir_proximos

    observacoes= [obs_simples("a"), obs_simples("b")]
    resultado= fundir_proximos([grupo((0.0, 0.0), [0]), grupo((2.0, 0.0), [1])], observacoes, 4.0)
    assert len(resultado) == 1
    assert {i for m in resultado[0] for i in m[1]} == {0, 1}


def test_nao_funde_elementos_que_partilham_uma_foto():
    from pipeline.geolocate.separar import fundir_proximos

    observacoes= [obs_simples("a"), obs_simples("a")]
    assert len(fundir_proximos([grupo((0.0, 0.0), [0]), grupo((2.0, 0.0), [1])], observacoes, 4.0)) == 2


def test_nao_funde_elementos_longe_ou_com_raio_zero():
    from pipeline.geolocate.separar import fundir_proximos

    observacoes= [obs_simples("a"), obs_simples("b")]
    longe= [grupo((0.0, 0.0), [0]), grupo((9.0, 0.0), [1])]
    perto= [grupo((0.0, 0.0), [0]), grupo((2.0, 0.0), [1])]
    assert len(fundir_proximos(longe, observacoes, 4.0)) == 2
    assert len(fundir_proximos(perto, observacoes, 0.0)) == 2


def test_fusao_em_cadeia_respeita_as_fotos_acumuladas():
    from pipeline.geolocate.separar import fundir_proximos

    observacoes= [obs_simples("a"), obs_simples("b"), obs_simples("a")]
    grupos= [grupo((0.0, 0.0), [0]), grupo((1.5, 0.0), [1]), grupo((3.0, 0.0), [2])]
    resultado= fundir_proximos(grupos, observacoes, 4.0)
    assert len(resultado) == 2
