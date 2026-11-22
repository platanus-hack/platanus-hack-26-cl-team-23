import asyncio
import itertools

from app.core.domain_errors import ValidationDomainError
from app.cv.tactics.forecast import FinishForecaster, ForecastConfig
from app.cv.tactics.overtake import OvertakeAdvisor, OvertakeConfig
from app.schemas.tactics import (
    Attack,
    ForecastAthlete,
    TacticsRequest,
    TacticsResult,
    TacticsStep,
)

MAX_ATTACKS = 3
# Un duelo solo vale si los dos se midieron hace poco: con datos viejos la brecha no sirve.
FRESH_S = 1.5

DISCLAIMER = (
    "Pronóstico de un modelo con parámetros supuestos (nivel del campo, reserva de energía, "
    "sprint final), no una medición: sirve para comparar escenarios, no como resultado."
)


class TacticsService:
    async def tactics(self, request: TacticsRequest) -> TacticsResult:
        """Pronóstico del final y mejores momentos para adelantar, causal y sin estado."""
        times = [f.t for f in request.frames]
        if any(b <= a for a, b in itertools.pairwise(times)):
            raise ValidationDomainError("'t' debe ser estrictamente creciente")
        steps = await asyncio.to_thread(self._run, request)
        return TacticsResult(
            distance=request.distance,
            t0=request.t0,
            every_s=request.every_s,
            steps=steps,
            disclaimer=DISCLAIMER,
        )

    @staticmethod
    def _run(request: TacticsRequest) -> list[TacticsStep]:
        forecaster = FinishForecaster(ForecastConfig(distance=request.distance), seed=request.seed)
        advisor = OvertakeAdvisor(
            OvertakeConfig(distance=request.distance, stale_s=FRESH_S),
            ForecastConfig(distance=request.distance),
            seed=request.seed,
        )
        steps: list[TacticsStep] = []
        next_sample = request.t0
        for frame in request.frames:
            if frame.t < request.t0 or not frame.athletes:
                continue
            athletes = [a.model_dump() for a in frame.athletes]
            forecaster.observe(frame.t, athletes)
            advisor.observe(frame.t, athletes)
            if frame.t < next_sample:
                continue
            next_sample = frame.t + request.every_s

            forecast = forecaster.forecast(frame.t)
            if not forecast["athletes"]:
                continue
            recs = [advisor.recommend(i, frame.t) for i in advisor.fresh(frame.t)]
            attacks = sorted((r for r in recs if r is not None), key=lambda r: -r["p_attack"])
            steps.append(
                TacticsStep(
                    t=frame.t,
                    winner=_clock(forecast["winner"], request.t0),
                    athletes=[
                        ForecastAthlete(**{**a, "eta": _clock(a["eta"], request.t0)})
                        for a in forecast["athletes"]
                    ],
                    attacks=[Attack(**r) for r in attacks[:MAX_ATTACKS]],
                )
            )
        return steps


def _clock(values: list[float] | None, t0: float) -> list[float] | None:
    """Del segundo del video al reloj de carrera (desde el disparo)."""
    return None if values is None else [round(v - t0, 1) for v in values]
