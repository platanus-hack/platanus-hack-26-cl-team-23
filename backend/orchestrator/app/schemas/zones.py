from typing import Annotated

from pydantic import BaseModel, Field

from app.cv.zones.evidence import DESC_SIZE, HIST_SIZE

Hist = Annotated[list[float], Field(min_length=HIST_SIZE, max_length=HIST_SIZE)]
Desc = Annotated[list[float], Field(min_length=DESC_SIZE, max_length=DESC_SIZE)]


class ZoneFeatures(BaseModel):
    t: float
    hist: Hist = Field(description="Histograma de color para detectar cortes de plano")
    desc: Desc | None = Field(
        default=None, description="Descriptor de apariencia (memoria de cámaras)"
    )
    bend: float | None = Field(
        default=None, description="Flecha/cuerda de las líneas pintadas (curvatura)"
    )
    chord: float | None = Field(
        default=None, description="Largo total de líneas medidas (px en 1280x720)"
    )
    n: int | None = Field(default=None, description="Trazos de línea usados")


class ZoneFeaturesResponse(BaseModel):
    frames: list[ZoneFeatures]


class ZoneFeaturesInput(BaseModel):
    """Features de un frame. `desc` y la curvatura son opcionales: basta con enviarlos cada
    ~0,5 s; `hist` hace falta en todos los frames para detectar cortes."""

    t: float = Field(ge=0, description="Segundos dentro del video")
    hist: Hist
    desc: Desc | None = None
    bend: float | None = Field(default=None, ge=0)
    chord: float | None = Field(default=None, ge=0)
    n: int | None = Field(default=None, ge=0)


class ZonesRequest(BaseModel):
    source: str = "upload"
    distance: float = Field(
        default=1500, gt=0, le=10000, description="Metros de la prueba (define salida y ritmo)"
    )
    t0: float = Field(
        default=0.0,
        description=(
            "Segundo del video en que suena el disparo (reloj de carrera). "
            "Negativo si el clip empieza con la carrera ya en marcha."
        ),
    )
    seed: int = 0
    cut_threshold: float = Field(default=0.19, gt=0, lt=1)
    frames: list[ZoneFeaturesInput] = Field(min_length=1, max_length=6000)


class ZoneFrame(BaseModel):
    frame: int = Field(description="Posición en la lista enviada (igual que 'frame' de /track)")
    t: float
    zone: int = Field(ge=1, le=6, description="Zona que enfoca la cámara, con histéresis")
    p: list[float] = Field(description="P(Z1..Z6)")
    s: float = Field(description="Metros desde la meta del punto enfocado (0-400)")
    x: float = Field(description="Metros recorridos desde la salida por el punto enfocado")
    x_std: float
    v: float = Field(description="Velocidad del punto enfocado (m/s)")
    cut: bool = Field(description="True si este frame empieza un plano nuevo")
    recognized: bool = Field(description="True si la memoria de cámaras reconoció el encuadre")


class ZonesResult(BaseModel):
    distance: float
    t0: float
    zone_names: dict[int, str]
    cuts: list[float]
    frames: list[ZoneFrame]
