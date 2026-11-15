from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ImageRecord:
    fonte: str
    id_fonte: str
    autor: str
    licenca: str
    url_origem: str
    capturada_em: datetime | None
    lon: float
    lat: float
    heading: float
    camera_type: str
    url_imagem: str
    width: int= 0
    height: int= 0
    caminho_anon: str | None= None

    @property
    def id(self) -> str:
        return f"{self.fonte}:{self.id_fonte}"


@dataclass(frozen=True)
class Detection:
    image_id: str
    category: str
    class_name: str
    bbox_xyxy: tuple[float, float, float, float]
    confidence: float
    obstruido: bool


@dataclass(frozen=True)
class Observation:
    detection: Detection
    image: ImageRecord
    bearing: float


@dataclass
class Element:
    category: str
    class_name: str
    lon: float
    lat: float
    obstruido: bool
    metodo_geo: str
    observations: list[Observation]= field(default_factory=list)
