from typing import Annotated, Self

from pydantic import BaseModel, Field, model_validator

# [x1, y1, x2, y2, conf, on_track]: caja en píxeles del video, confianza del detector
# y fracción (0-1) de color pista bajo los pies.
RawDetection = Annotated[list[float], Field(min_length=6, max_length=6)]


class VideoInfo(BaseModel):
    source: str
    width: int
    height: int
    fps_src: float
    fps_out: float
    frames: int
    duration_s: float


class PipelineInfo(BaseModel):
    detector: str
    tracker: str
    min_det_conf: float
    min_on_track: float
    min_track_on_track: float
    roi: list[tuple[float, float]] | None = None


class TrackSummary(BaseModel):
    id: int
    t_start: float
    t_end: float
    n_obs: int
    on_track: float


class TrackedDetection(BaseModel):
    id: int
    bbox: list[float]
    foot_px: list[float]
    conf: float


class TrackedFrame(BaseModel):
    frame: int
    t: float
    detections: list[TrackedDetection]


class TrackingResult(BaseModel):
    video: VideoInfo
    pipeline: PipelineInfo
    tracks: list[TrackSummary]
    frames: list[TrackedFrame]


class DetectedFrame(BaseModel):
    t: float
    dets: list[RawDetection]


class DetectResponse(BaseModel):
    model: str
    frames: list[DetectedFrame]


class TrackFrameInput(BaseModel):
    t: float = Field(ge=0, description="Segundos dentro del video")
    dets: list[RawDetection]


class TrackRequest(BaseModel):
    source: str = "upload"
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps_out: float = Field(default=15.0, ge=1, le=60)
    fps_src: float | None = Field(default=None, gt=0)
    frames: list[TrackFrameInput] = Field(min_length=1, max_length=1500)


class ProcessRequest(BaseModel):
    source: str | None = Field(default=None, description="Video de ejemplo, p. ej. 'NCCA'")
    blob: str | None = Field(default=None, description="Ruta en el store, p. ej. 'videos/x.mp4'")
    fps: float = Field(default=15.0, ge=1, le=30)

    @model_validator(mode="after")
    def _exactly_one_source(self) -> Self:
        if (self.source is None) == (self.blob is None):
            raise ValueError("Indica exactamente uno: 'source' o 'blob'")
        return self


class ProcessResponse(BaseModel):
    key: str
    cached: bool
    result_path: str = Field(description="Ruta del resultado: GET /api/tracking/results/{key}")
    result_url: str | None = Field(default=None, description="URL pública directa (Blob)")
    result: TrackingResult | None = Field(
        default=None, description="Resultado en línea si es liviano; si no, usar result_url"
    )
