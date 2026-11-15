import math

FOV_PADRAO= 65.0
FOV_VERTICAL_ESFERICA= 180.0


def horizontal_fov(camera_type: str) -> float:
    return 360.0 if camera_type == "spherical" else FOV_PADRAO


def vertical_fov(camera_type: str, width: int, height: int) -> float:
    if camera_type == "spherical":
        return FOV_VERTICAL_ESFERICA
    return FOV_PADRAO * height / width


def object_bearing(heading: float, x_center: float, width: int, fov: float) -> float:
    return (heading + (x_center / width - 0.5) * fov) % 360.0


def monocular_distance(altura_m: float, bbox_height: float, image_height: int, fov_v: float) -> float | None:
    if bbox_height <= 0:
        return None
    angulo= math.radians(bbox_height / image_height * fov_v)
    return altura_m / (2 * math.tan(angulo / 2))
