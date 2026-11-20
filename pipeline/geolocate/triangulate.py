import math

ALCANCE_MAX_M= 60.0
ANGULO_MIN_GRAUS= 10.0
DISTANCIA_MAX_ORIGENS_M= 30.0


def direction(bearing: float) -> tuple[float, float]:
    rad= math.radians(bearing)
    return math.sin(rad), math.cos(rad)


def intersect(
    p1: tuple[float, float],
    b1: float,
    p2: tuple[float, float],
    b2: float,
    alcance_m: float= ALCANCE_MAX_M,
) -> tuple[float, float] | None:
    diferenca= abs((b1 - b2 + 180.0) % 360.0 - 180.0)
    if not ANGULO_MIN_GRAUS < diferenca < 180.0 - ANGULO_MIN_GRAUS:
        return None
    d1x, d1y= direction(b1)
    d2x, d2y= direction(b2)
    rx, ry= p2[0] - p1[0], p2[1] - p1[1]
    det= d2x * d1y - d1x * d2y
    t1= (d2x * ry - d2y * rx) / det
    t2= (d1x * ry - d1y * rx) / det
    if not 0 < t1 <= alcance_m or not 0 < t2 <= alcance_m:
        return None
    return p1[0] + t1 * d1x, p1[1] + t1 * d1y
