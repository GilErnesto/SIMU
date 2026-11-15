import numpy as np
from sklearn.cluster import DBSCAN


def cluster(points: np.ndarray, radius_m: float) -> np.ndarray:
    return DBSCAN(eps=radius_m, min_samples=1).fit_predict(points)
