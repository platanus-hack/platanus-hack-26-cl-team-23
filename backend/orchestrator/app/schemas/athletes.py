from typing import Annotated

from pydantic import BaseModel, Field

from app.cv.athletes.measure import JERSEY_SIZE

Jersey = Annotated[list[float], Field(min_length=JERSEY_SIZE, max_length=JERSEY_SIZE)]
# [id, x1, y1, x2, y2]: id del tracker de imagen (salida de /track; -1 si no hay) y caja en
# píxeles del video original
TrackedBox = Annotated[list[float], Field(min_length=5, max_length=5)]


class RunnerFeatures(BaseModel):
    id: int | None = Field(description="id del tracker de imagen (/track)")
    bbox: list[float] = Field(description="[x1, y1, x2, y2] en píxeles del video original")
    foot: list[float]
    ds: float = Field(description="m relativo al centro del grupo, en el sentido de u_img")
    sigma_ds: float
    d: float | None = Field(description="m al bordillo (None si no se pudo medir)")
    sigma_d: float | None
    jersey: Jersey | None = Field(description="Color de camiseta (re-identificación tras cortes)")


class AthleteFrameFeatures(BaseModel):
    t: float = Field(ge=0, description="Segundos dentro del video")
    u_img: list[float] | None = Field(
        description="Dirección de imagen sobre la que se midió ds (None: sin geometría)"
    )
    head_on: bool = Field(description="La pista se aleja de la cámara (ds es profundidad)")
    blind: bool = Field(description="Primer plano sin geometría confiable: no hay medición")
    bg_shift: list[float] | None = Field(
        description="Movimiento del fondo (px) desde el frame anterior del mismo lote"
    )
    runners: list[RunnerFeatures]


class AthleteFeaturesResponse(BaseModel):
    frames: list[AthleteFrameFeatures]


class GroupInput(BaseModel):
    """Una fila de la salida de /zones para el mismo frame."""

    x: float = Field(description="Metros recorridos por la cabeza de carrera ('x' de /zones)")
    v: float = Field(description="Su velocidad ('v' de /zones)")
    cut: bool = False


class AthletesRequest(BaseModel):
    source: str = "upload"
    t0: float = Field(
        default=0.0, description="Segundo del video del disparo (negativo: ya empezó)"
    )
    field_size: int = Field(default=12, ge=1, le=40, description="Corredores en la serie")
    distance: float = Field(
        default=1500,
        gt=0,
        le=10000,
        description="Metros de la prueba: define dónde está la salida (el mismo de /zones)",
    )
    frames: list[AthleteFrameFeatures] = Field(min_length=1, max_length=6000)
    group: list[GroupInput] = Field(min_length=1, max_length=6000)


class AthleteState(BaseModel):
    id: int = Field(description="Atleta (estable a través de cortes de plano)")
    track_id: int | None = Field(description="id del tracker de imagen en este frame, si se ve")
    rank: int = Field(description="Puesto entre los atletas vistos en los últimos 3 s")
    x: float = Field(description="Metros recorridos desde la salida")
    s: float = Field(
        description="Metros desde la meta en sentido de carrera (0-400), contando desde la salida de la prueba"
    )
    d: float = Field(description="Metros al bordillo")
    lane: int = Field(description="Calle (1 = la de adentro)")
    v: float = Field(description="Velocidad respecto a la cancha (m/s)")
    u: float = Field(description="Velocidad relativa al grupo (m/s)")
    visible: bool
    sigma_x: float = Field(description="Incertidumbre de x relativa al grupo (m)")
    bbox: list[float] | None


class GroupOutput(BaseModel):
    x: float
    v: float


class AthletesFrame(BaseModel):
    frame: int = Field(description="Posición en la lista enviada (igual que /track y /zones)")
    t: float
    group: GroupOutput
    measured: bool = Field(description="Hubo geometría para medir en este frame")
    athletes: list[AthleteState]


class AthletesResult(BaseModel):
    t0: float
    frames: list[AthletesFrame]
