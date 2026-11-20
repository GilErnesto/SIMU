import numpy as np

from pipeline.geolocate.triangulate import direction

DISTANCIA_MIN_M= 5.0
CONDICAO_MAX= 1e3


def _resolver(origens: np.ndarray, direcoes: np.ndarray, pesos: np.ndarray) -> np.ndarray | None:
    a= np.zeros((2, 2))
    b= np.zeros(2)
    for peso, d, origem in zip(pesos, direcoes, origens):
        m= peso * (np.eye(2) - np.outer(d, d))
        a+= m
        b+= m @ origem
    if np.linalg.cond(a) > CONDICAO_MAX:
        return None
    return np.linalg.solve(a, b)


def ponto_minimos_quadrados(
    origens: list[tuple[float, float]], rumos: list[float]
) -> tuple[float, float] | None:
    pontos= np.array(origens, dtype=float)
    direcoes= np.array([direction(rumo) for rumo in rumos])
    ponto= _resolver(pontos, direcoes, np.ones(len(pontos)))
    if ponto is None:
        return None
    distancias= np.maximum(np.hypot(*(pontos - ponto).T), DISTANCIA_MIN_M)
    ponto= _resolver(pontos, direcoes, 1.0 / distancias**2)
    if ponto is None:
        return None
    if np.any(np.einsum("ij,ij->i", ponto - pontos, direcoes) <= 0):
        return None
    return float(ponto[0]), float(ponto[1])
