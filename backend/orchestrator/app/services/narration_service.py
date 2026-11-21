"""Relato de la carrera: hechos deterministas → guion (Claude) → voz (ElevenLabs).

Tres ideas sostienen que el relato sea concordante con los datos:

1. El modelo no ve el JSON de /track. Ve una hoja de hechos ya resumida (`race_facts`),
   con la lista explícita de lo que puede y de lo que no puede afirmar.
2. El guion se pide con `tool_choice` obligado: la respuesta siempre tiene la forma
   esperada, así que no hay reintentos por JSON roto.
3. Antes de gastar un solo carácter de ElevenLabs, el texto se valida: presupuesto de
   palabras, cifras que existan en los hechos y léxico de resultado prohibido.
   Si no pasa, se reintenta una vez; si vuelve a fallar, se usan plantillas.
"""

import asyncio
import hashlib
import itertools
import json
import math
import re

from anthropic import AsyncAnthropic
from elevenlabs.client import AsyncElevenLabs

from app.clients.storage import Storage
from app.core.config import settings
from app.core.domain_errors import ExternalServiceError, NotFoundError, ValidationDomainError
from app.core.logger import logger
from app.cv.race_facts import allowed_numbers, build_facts
from app.schemas.narration import NarrationRequest, NarrationResponse, NarrationSegment

# Ritmo medido de la voz real (Eleven v4, español): ~2,5 palabras/s. Se deja un margen
# porque las cifras y las pausas lo bajan. Si nos pasamos, la voz invade el tramo siguiente.
WORDS_PER_SECOND = 2.35
# Margen antes de considerar que el guion se sale del tiempo disponible.
WORD_GRACE = 3
# Los modelos no cuentan palabras con precisión: se tolera un 35 % de más antes de
# descartar un guion bueno. La duración real de cada audio se mide después.
WORD_TOLERANCE = 1.35
# Tope de tramos: más que esto no se alcanza a decir en el clip.
MAX_SEGMENTS = 12
# Si el modelo se demora más que esto, mejor plantillas que una demo colgada.
LLM_TIMEOUT_S = 30.0
# Súbelo al tocar el prompt o las reglas de validación: invalida los guiones en caché.
PROMPT_VERSION = 4
# Cuánto puede pasarse la voz de su ventana antes de pedir un recorte (una sola vez).
# El front acelera hasta 1,35× para encajar cada tramo; por debajo de eso no vale la pena
# gastar otra llamada al modelo.
MAX_OVERRUN = 1.3

_KEY_PATTERN = re.compile(r"^[a-f0-9]{16,64}$")
_DIGIT = re.compile(r"\d+(?:[.,]\d+)?")
_TRACK_REF = re.compile(r"#\s*\d+")
# Afirmaciones de resultado que el sistema no puede sostener: no mide la posición de nadie.
_BANNED = re.compile(
    r"\b(gana|ganó|ganando|ganador|lidera|liderando|líder|remontó|remonta|remontada|"
    r"adelantó|adelanta|adelantamiento|récord|oro|plata|bronce|medalla|podio|"
    r"primero|segundo|tercero|último lugar|"
    # También delata una posición que no medimos.
    r"comanda|comandando|impone|marca el ritmo|al frente|en punta|cabeza de carrera|"
    r"se escapa|escapó|saca ventaja|ventaja|saca distancia|persigue|pegado)\b",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """\
Eres relator de atletismo para televisión chilena. Comentas un clip que un sistema de \
visión computacional ya analizó. Lo que escribas se escucha encima del video: tiene que \
sonar a transmisión, no a informe.

Recibes un JSON con HECHOS. Es la ÚNICA fuente de verdad.

TONO
- Presente, energía contenida, ritmo de transmisión en vivo. Nada de leer datos.
- Frases cortas. Alterna golpes de cuatro a seis palabras con una frase más larga que respire.
- Recursos de relator: nombrar quién entra y quién sale de cuadro, acompañar el movimiento \
del encuadre como si siguieras la acción, cerrar con una imagen.
- Habla del encuadre, la toma o el plano; nunca digas "la cámara" como si fuera un aparato.
- Prohibido el relleno: "espectacular", "increíble", "sin palabras", "como pueden ver", \
"bueno", "eh", "amigos", "señoras y señores".
- Prohibido sonar a resumen escolar: si una frase no aporta una imagen o un dato, bórrala.

REGLAS DURAS
1. Nombres: los corredores se llaman solo "#" + su id. No inventes nombres, dorsales, \
nacionalidades ni clubes.
2. Prohibido afirmar posiciones, quién lidera, quién adelanta o quién gana: el sistema no \
mide la posición de cada atleta en la pista. Si lo dices, mientes.
3. Todo número que menciones debe estar en HECHOS. Prohibido redondear, estimar o inventar \
tiempos, metros, récords o marcas.
4. Habla solo de: cuántos corredores siguen, cuántos caben en cuadro, cuándo aparece o se \
pierde uno, qué tramo de pista enfoca la cámara, cuánto lo recorre, si hubo cortes de plano.
5. Nunca menciones el modelo, el algoritmo, ByteTrack, Roboflow ni "la IA". Puedes decir \
"el seguimiento".
6. Español de Chile neutro, registro televisivo.
7. No cierres con un resultado: no hay resultado que informar. Cierra con lo que se ve.

FORMATO
Devuelve los segmentos con la herramienta `relato`. Cubren el clip completo, sin huecos \
ni solapes, en orden. Respeta el máximo de palabras de cada tramo.
"""

NARRATION_SCHEMA = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "text": {"type": "string"},
                },
                "required": ["start", "end", "text"],
            },
        },
        "disclaimer": {
            "type": "string",
            "description": "Una frase que aclare qué no mide el sistema",
        },
    },
    "required": ["segments", "disclaimer"],
}

DEFAULT_DISCLAIMER = (
    "El seguimiento ubica a los corredores en la imagen, no su posición en metros sobre la pista."
)

STYLE_HINT = {
    "transmision": (
        "transmisión en vivo: energía alta, frases que se pisan, la sensación de estar "
        "siguiendo la acción con la mirada"
    ),
    "analisis": (
        "análisis de entrenador al borde de la pista: pausado, preciso, sin adornos, "
        "cada frase con una observación concreta"
    ),
}


def _mp3_seconds(data: bytes) -> float | None:
    """Duración del mp3 sin decodificarlo: ElevenLabs entrega 128 kbps constantes."""
    return round(len(data) * 8 / 128_000, 2) if data else None


def _as_text(segments: list[NarrationSegment]) -> str:
    return "\n".join(
        f"[{s.start:.1f}-{s.end:.1f} s] ({len(s.text.split())} palabras) {s.text}" for s in segments
    )


class NarrationService:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    async def narrate(self, request: NarrationRequest) -> NarrationResponse:
        facts = build_facts(request.tracks, request.zones)
        duration = request.tracks.video.duration_s
        if duration <= 0:
            raise ValidationDomainError("El video no tiene duración: no se puede relatar")
        if not request.tracks.frames:
            raise ValidationDomainError("No hay cuadros que relatar")

        key = self._key(facts, request)
        stored = await self._storage.get(f"narration/{key}.json")
        if stored is not None:
            return self._response(key, True, json.loads(stored))

        windows = self._windows(duration, request.segment_s)
        segments, source, disclaimer = await self._script(facts, windows, request)
        durations = await self._synthesize(key, segments)

        # El largo del texto no se puede pedir con precisión, pero sí se puede medir. Si algún
        # tramo se pasa de su ventana, se pide UN recorte con la cifra real en la mano.
        worst = max(
            (length or 0) / max(0.5, segment.end - segment.start)
            for segment, length in zip(segments, durations, strict=True)
        )
        if source == "llm" and worst > MAX_OVERRUN:
            segments, disclaimer, durations = await self._condense(
                facts, windows, request, segments, disclaimer, durations, duration, key
            )

        for segment, length in zip(segments, durations, strict=True):
            segment.duration_s = length

        has_audio = bool(durations) and durations[0] is not None
        payload = {
            "source": source,
            "disclaimer": disclaimer,
            "segments": [s.model_dump() for s in segments],
            "audio": [f"/api/narration/{key}/audio/{i}" for i in range(len(durations))]
            if has_audio
            else [],
            "characters": sum(len(s.text) for s in segments) if has_audio else 0,
        }
        await self._storage.put(
            f"narration/{key}.json", json.dumps(payload).encode(), "application/json"
        )
        return self._response(key, False, payload)

    # ------------------------------------------------------------------ guion

    async def _script(
        self, facts: dict, windows: list[tuple[float, float]], request: NarrationRequest
    ) -> tuple[list[NarrationSegment], str, str]:
        """Intenta Claude; si no está disponible o el texto no pasa la validación, plantillas."""
        if settings.anthropic_api_key:
            feedback: str | None = None
            for attempt in (1, 2):
                try:
                    segments, disclaimer = await self._ask_claude(facts, windows, request, feedback)
                except Exception as exc:  # noqa: BLE001 - cualquier fallo cae a plantillas
                    logger.warning("Relato: Claude falló (%s)", exc)
                    break
                problem = self._validate(segments, windows, facts)
                if problem is None:
                    logger.info("Relato: guion de Claude en el intento %d", attempt)
                    return segments, "llm", disclaimer
                logger.warning("Relato: guion descartado en intento %d: %s", attempt, problem)
                # El segundo intento ve su propio texto y qué se corrigió: sin eso vuelve a fallar igual.
                feedback = f"{problem}\nTu intento anterior fue:\n{_as_text(segments)}"
        return self._template_script(facts, windows), "template", DEFAULT_DISCLAIMER

    async def _ask_claude(
        self,
        facts: dict,
        windows: list[tuple[float, float]],
        request: NarrationRequest,
        feedback: str | None = None,
    ) -> tuple[list[NarrationSegment], str]:
        budget = "\n".join(
            f"- {start:.1f}-{end:.1f} s: máximo {self._max_words(start, end)} palabras "
            f"(apunta a {self._target_words(start, end)})"
            for start, end in windows
        )
        total = self._max_total_words(windows[-1][1])
        user = (
            f"HECHOS:\n{json.dumps(facts, ensure_ascii=False)}\n\n"
            "CÓMO LEER LOS HECHOS (usa cada cifra solo para lo que dice aquí)\n"
            "- runners.total: corredores distintos seguidos en todo el clip.\n"
            "- runners.peak_on_screen / median_on_screen: cuántos caben en cuadro a la vez.\n"
            "- tracks[].in_s / out_s: cuándo aparece y cuándo se pierde de cuadro cada uno.\n"
            "- camera.span_m: metros de pista que recorrió el encuadre en TODO el clip; "
            "es la única cifra para decir cuánto se movió la cámara.\n"
            "- camera.timeline[]: qué zona enfoca y en qué ventana de tiempo.\n"
            "- camera.pan_speed_mps: velocidad del barrido del encuadre.\n"
            "- camera.cuts: cambios de plano.\n\n"
            f"Clip de {windows[-1][1]:.1f} s, dividido en {len(windows)} tramos:\n{budget}\n\n"
            f"El guion completo no puede pasar de {total} palabras.\n"
            "La voz se lee a ~2,2 palabras por segundo: pasarse significa que un tramo se "
            "pisa con el siguiente. Prefiere escribir números con cifras (12, no «doce»): "
            "se leen más rápido. Cuenta las palabras antes de responder; si dudas, escribe "
            "menos, no más.\n\n"
            f"Tono: {STYLE_HINT[request.style]}\n"
            "Escribe como si el video ya estuviera corriendo: sin introducir ni despedir.\n"
        )
        if feedback:
            user += f"\nCORRIGE ESTO DEL INTENTO ANTERIOR:\n{feedback}\n"
        user += "Escribe el relato con la herramienta `relato`."
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await asyncio.wait_for(
            client.messages.create(
                model=settings.anthropic_model,
                max_tokens=1500,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        # El prompt de sistema no cambia nunca: cachearlo abarata cada relato.
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user}],
                tools=[
                    {
                        "name": "relato",
                        "description": "Guion del relato, segmentado por tramos del clip",
                        "input_schema": NARRATION_SCHEMA,
                    }
                ],
                tool_choice={"type": "tool", "name": "relato"},
            ),
            timeout=LLM_TIMEOUT_S,
        )
        block = next((b for b in response.content if getattr(b, "type", None) == "tool_use"), None)
        if block is None:
            raise ExternalServiceError("Claude no devolvió el guion", code="narration_failed")
        data = block.input
        segments = [
            NarrationSegment(
                start=float(s["start"]), end=float(s["end"]), text=str(s["text"]).strip()
            )
            for s in data["segments"]
        ]
        return segments, str(data.get("disclaimer") or DEFAULT_DISCLAIMER)

    async def _condense(
        self,
        facts: dict,
        windows: list[tuple[float, float]],
        request: NarrationRequest,
        segments: list[NarrationSegment],
        disclaimer: str,
        durations: list[float | None],
        duration: float,
        key: str,
    ) -> tuple[list[NarrationSegment], str, list[float | None]]:
        """Una segunda pasada con la duración real medida: el modelo sí sabe recortar si
        le dicen cuántos segundos sobraron. Si algo falla, se queda el guion original."""
        spoken = sum(d or 0 for d in durations)
        worst = max(
            (d or 0) / max(0.5, s.end - s.start) for s, d in zip(segments, durations, strict=True)
        )
        words = sum(len(s.text.split()) for s in segments)
        # Se apunta al clip completo, descontando medio segundo de silencio por tramo.
        target = max(len(windows), math.floor((duration - 0.5 * len(windows)) / 2.1))
        feedback = (
            f"El audio de este guion dura {spoken:.1f} s para un clip de {duration:.1f} s: "
            f"el tramo más largo se pasa {worst:.1f} veces de su ventana. Reescríbelo con un "
            f"máximo de {target} palabras en total (ahora tiene {words}), repartidas en los "
            f"mismos {len(windows)} tramos, sin perder ningún hecho."
        )
        try:
            shorter, new_disclaimer = await self._ask_claude(facts, windows, request, feedback)
            problem = self._validate(shorter, windows, facts)
            if problem is not None:
                logger.warning("Relato: recorte descartado (%s)", problem)
                return segments, disclaimer, durations
            new_durations = await self._synthesize(key, shorter)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Relato: el recorte falló (%s); queda el guion original", exc)
            return segments, disclaimer, durations

        if sum(d or 0 for d in new_durations) >= spoken:
            return segments, disclaimer, durations
        logger.info(
            "Relato: recortado de %.1fs a %.1fs", spoken, sum(d or 0 for d in new_durations)
        )
        return shorter, new_disclaimer, new_durations

    def _validate(
        self, segments: list[NarrationSegment], windows: list[tuple[float, float]], facts: dict
    ) -> str | None:
        """Devuelve el problema encontrado, o None si el guion se puede usar."""
        if not segments:
            return "no devolvió segmentos"
        if len(segments) > MAX_SEGMENTS:
            return f"devolvió {len(segments)} tramos y el máximo es {MAX_SEGMENTS}"

        allowed = allowed_numbers(facts)
        track_ids = {float(t["id"]) for t in facts["tracks"]}
        ordered = sorted(segments, key=lambda s: s.start)

        if ordered[0].start > 0.6:
            return "el primer tramo no empieza al inicio del clip"
        if ordered[-1].end < windows[-1][1] - 1.0:
            return "el último tramo no llega al final del clip"
        for previous, current in itertools.pairwise(ordered):
            if current.start - previous.end > 0.6:
                return f"hay un hueco entre {previous.end:.1f}s y {current.start:.1f}s"

        # El largo NO se rechaza: los modelos no cuentan palabras de forma fiable y
        # reintentar por eso empeora el texto. Se avisa y el front ajusta la velocidad
        # de reproducción para que la voz termine junto con el clip.
        total_words = 0
        for segment in ordered:
            words = len(segment.text.split())
            total_words += words
            if words > self._max_words(segment.start, segment.end):
                logger.info(
                    "Relato: tramo %.0f-%.0fs con %d palabras (objetivo ≤%d); se ajustará la velocidad",
                    segment.start,
                    segment.end,
                    words,
                    self._max_words(segment.start, segment.end),
                )
            banned = _BANNED.search(segment.text)
            if banned:
                return f"afirma un resultado que no podemos sostener: {banned.group(0)!r}"
            for raw in self._numbers(segment.text):
                if raw in track_ids and raw.is_integer():
                    continue  # es el id de un corredor
                if not any(abs(raw - value) <= 0.15 for value in allowed):
                    return f"usa la cifra {raw} que no está en los hechos"

        max_total = self._max_total_words(windows[-1][1])
        if total_words > max_total:
            logger.info("Relato: %d palabras en total (objetivo ≤%d)", total_words, max_total)
        return None

    @staticmethod
    def _numbers(text: str) -> list[float]:
        """Cifras del texto, sin contar las que van pegadas a un '#' (ids de corredor)."""
        clean = _TRACK_REF.sub(" ", text)
        return [float(m.replace(",", ".")) for m in _DIGIT.findall(clean)]

    # ------------------------------------------------------------- plantillas

    def _template_script(
        self, facts: dict, windows: list[tuple[float, float]]
    ) -> list[NarrationSegment]:
        """Respaldo sin IA: frases armadas solo con los hechos. Seco, pero nunca miente."""
        camera = facts.get("camera")
        runners = facts["runners"]
        phrases = [
            f"Arranca el clip con {runners['peak_on_screen']} corredores en cuadro.",
            f"El seguimiento confirma {runners['total']} atletas sobre la pista.",
        ]
        if camera:
            for step in camera["timeline"][:2]:
                phrases.append(
                    f"El encuadre pasa por {step['zone_name']} "
                    f"y recorre {camera['span_m']} metros de pista."
                )
            phrases.append(
                "Sin cortes de plano."
                if camera["cuts"] == 0
                else f"{camera['cuts']} cambios de plano."
            )
        phrases.append(
            f"Se mantienen en cuadro {runners['median_on_screen']} corredores en promedio."
        )

        return [
            NarrationSegment(
                start=round(start, 1),
                end=round(end, 1),
                text=phrases[i % len(phrases)],
            )
            for i, (start, end) in enumerate(windows)
        ]

    # ---------------------------------------------------------------- voz

    async def _synthesize(self, key: str, segments: list[NarrationSegment]) -> list[float | None]:
        """Una petición por tramo. Devuelve la duración de cada audio."""
        if not settings.eleven_labs_api_key:
            logger.info("Relato: sin ELEVEN_LABS_API_KEY, se devuelve solo el texto")
            return [None] * len(segments)

        client = AsyncElevenLabs(api_key=settings.eleven_labs_api_key)
        durations: list[float | None] = []
        for index, segment in enumerate(segments):
            try:
                stream = client.text_to_speech.convert(
                    text=segment.text,
                    voice_id=settings.eleven_labs_voice_id,
                    model_id=settings.eleven_labs_model,
                    output_format="mp3_44100_128",
                )
                audio = b"".join([chunk async for chunk in stream])
            except Exception as exc:
                raise ExternalServiceError(
                    f"ElevenLabs no pudo sintetizar el tramo {index}", code="tts_failed"
                ) from exc
            pathname = f"narration/{key}-{index}.mp3"
            await self._storage.put(pathname, audio, "audio/mpeg")
            durations.append(_mp3_seconds(audio))
        logger.info(
            "Relato: %d tramos sintetizados, %d caracteres, %.1f s de audio",
            len(durations),
            sum(len(s.text) for s in segments),
            sum(d or 0 for d in durations),
        )
        return durations

    async def audio(self, key: str, index: int) -> bytes:
        if not _KEY_PATTERN.fullmatch(key):
            raise ValidationDomainError("Clave de relato inválida")
        data = await self._storage.get(f"narration/{key}-{index}.mp3")
        if data is None:
            raise NotFoundError(f"No hay audio para el tramo {index} de ese relato")
        return data

    # ------------------------------------------------------------ auxiliares

    @staticmethod
    def _windows(duration: float, segment_s: float) -> list[tuple[float, float]]:
        count = max(1, min(MAX_SEGMENTS, round(duration / segment_s)))
        step = duration / count
        return [(round(i * step, 2), round((i + 1) * step, 2)) for i in range(count)]

    @staticmethod
    def _target_words(start: float, end: float) -> int:
        return math.ceil(WORDS_PER_SECOND * max(0.5, end - start))

    @classmethod
    def _max_words(cls, start: float, end: float) -> int:
        return math.ceil(cls._target_words(start, end) * WORD_TOLERANCE) + WORD_GRACE

    @staticmethod
    def _max_total_words(duration: float) -> int:
        return math.ceil(WORDS_PER_SECOND * duration * WORD_TOLERANCE) + WORD_GRACE

    @staticmethod
    def _key(facts: dict, request: NarrationRequest) -> str:
        """Mismo video y mismo estilo → mismo relato, sin volver a gastar cuota."""
        material = json.dumps(
            {
                "facts": facts,
                "style": request.style,
                "segment_s": request.segment_s,
                "voice": settings.eleven_labs_voice_id,
                "tts": settings.eleven_labs_model,
                "llm": settings.anthropic_model,
                "prompt": PROMPT_VERSION,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(material.encode()).hexdigest()[:16]

    @staticmethod
    def _response(key: str, cached: bool, payload: dict) -> NarrationResponse:
        return NarrationResponse(
            key=key,
            cached=cached,
            source=payload["source"],
            disclaimer=payload["disclaimer"],
            segments=[NarrationSegment(**s) for s in payload["segments"]],
            audio=payload["audio"],
            characters=payload["characters"],
        )
