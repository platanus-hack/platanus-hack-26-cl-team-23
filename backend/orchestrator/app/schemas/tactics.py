from typing import Literal

from pydantic import BaseModel, Field


class TacticsAthlete(BaseModel):
    id: int = Field(description="Atleta (el mismo id de /api/athletes/)")
    x: float = Field(description="Metros recorridos desde la salida")
    v: float = Field(ge=0, description="Velocidad respecto a la cancha (m/s)")
    d: float = Field(default=0.0, description="Metros al bordillo")
    sigma_x: float = Field(default=0.5, ge=0, description="Incertidumbre de x (m)")


class TacticsFrame(BaseModel):
    t: float = Field(description="Segundos dentro del video")
    athletes: list[TacticsAthlete] = Field(description="Solo los medidos en este cuadro")


class TacticsRequest(BaseModel):
    source: str = "upload"
    distance: float = Field(
        default=1500, gt=0, le=10000, description="Metros de la prueba (el mismo de /zones)"
    )
    t0: float = Field(default=0.0, description="Segundo del video en que suena el disparo")
    every_s: float = Field(
        default=1.0, ge=0.1, le=5.0, description="Cada cuántos segundos se calcula un pronóstico"
    )
    seed: int = 0
    frames: list[TacticsFrame] = Field(min_length=1, max_length=6000)


class ForecastAthlete(BaseModel):
    id: int
    x: float = Field(description="Metros recorridos (extrapolados al instante del pronóstico)")
    v: float = Field(description="Ritmo actual suavizado (m/s)")
    eta: list[float] = Field(
        min_length=3,
        max_length=3,
        description="Llegada estimada en segundos de carrera (reloj desde el disparo): p10, p50, p90",
    )
    p_win: float = Field(ge=0, le=1, description="Probabilidad de ganar entre los medidos")
    p_podium: float = Field(ge=0, le=1, description="Probabilidad de podio entre los medidos")
    exp_rank: float = Field(description="Puesto esperado entre los medidos")


class Attack(BaseModel):
    id: int = Field(description="Atleta que ataca")
    rival: int = Field(description="Atleta de adelante, al que pasaría")
    action: Literal["attack", "wait", "hold"] = Field(
        description="attack: la ventana está abierta ahora; wait: esperar a un punto más "
        "adelante; hold: no hay opción razonable, seguir a rebufo"
    )
    p_attack: float = Field(ge=0, le=1, description="P(llegar antes que el rival) en el punto")
    p_now: float = Field(ge=0, le=1, description="P(llegar antes que el rival) atacando ya")
    at_m: float = Field(description="Metros que le faltan al rival en el punto recomendado")
    zone: int = Field(ge=1, le=6, description="Zona de la pista de ese punto (como en /zones)")
    gap: float = Field(description="Metros que separan a los dos ahora")
    remaining: float = Field(description="Metros que le faltan al rival ahora")
    window: list[float] = Field(
        min_length=2,
        max_length=2,
        description="Ventana de ataque en metros que faltan al rival: (desde, hasta), desde >= hasta",
    )
    reserve: float = Field(description="Reserva de energía del atacante (0-1, mediana)")
    rival_reserve: float = Field(description="Reserva de energía del rival (0-1, mediana)")
    draft_m: float = Field(description="Metros que el atacante lleva a rebufo")
    extra_m: float = Field(description="Metros extra que cuesta pasar por fuera en ese punto")
    curve: list[list[float]] = Field(
        description="[[metros que faltan, P(adelantar)], ...] de lejos a cerca de la meta"
    )


class TacticsStep(BaseModel):
    t: float = Field(description="Segundo del video del pronóstico")
    winner: list[float] | None = Field(
        description="Tiempo ganador pronosticado (s de carrera): p10, p50, p90"
    )
    athletes: list[ForecastAthlete] = Field(description="Por puesto esperado")
    attacks: list[Attack] = Field(description="Las mejores oportunidades, de mayor a menor P")


class TacticsResult(BaseModel):
    distance: float
    t0: float
    every_s: float
    steps: list[TacticsStep]
    disclaimer: str = Field(
        description="Esto es un pronóstico de un modelo con parámetros supuestos, no una medición"
    )
