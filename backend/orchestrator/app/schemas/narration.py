from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.tracking import TrackingResult
from app.schemas.zones import ZonesResult


class NarrationRequest(BaseModel):
    tracks: TrackingResult = Field(description="Salida de /api/tracking/track")
    zones: ZonesResult | None = Field(
        default=None,
        description="Salida de /api/zones/ (opcional: sin ella no hay relato de cámara)",
    )
    style: Literal["transmision", "analisis"] = Field(
        default="transmision", description="Registro del relato"
    )
    segment_s: float = Field(
        default=8.0, ge=2, le=15, description="Duración objetivo de cada tramo narrado"
    )


class NarrationSegment(BaseModel):
    start: float = Field(description="Segundo del video en que empieza este tramo")
    end: float = Field(description="Segundo del video en que termina")
    text: str
    duration_s: float | None = Field(
        default=None,
        description="Duración real del audio. Puede superar la ventana: entonces la voz "
        "termina después del corte y el front encadena los tramos sin cortar palabras.",
    )


class NarrationResponse(BaseModel):
    key: str
    cached: bool
    source: Literal["llm", "template"] = Field(description="De dónde salió el guion")
    disclaimer: str = Field(description="Qué NO mide el sistema; se muestra al pie")
    segments: list[NarrationSegment]
    audio: list[str] = Field(
        description="URL de cada segmento: GET /api/narration/{key}/audio/{index}"
    )
    characters: int = Field(description="Caracteres enviados a ElevenLabs (su unidad de cobro)")
