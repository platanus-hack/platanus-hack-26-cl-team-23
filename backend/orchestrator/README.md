# Orchestrator API

API FastAPI del proyecto, gestionada con [uv](https://docs.astral.sh/uv/).

## Requisitos

- Python 3.13+
- uv

## Setup

```bash
cd backend/orchestrator
uv sync
cp .env.example .env   # obligatorio: todas las variables son requeridas
```

> La app falla al arrancar con `Missing required environment variable: <NAME>` si falta
> cualquier variable. No hay valores por defecto para la configuración.

## Comandos

```bash
uv run poe dev     # servidor con reload en http://localhost:8080
uv run poe test    # tests con pytest
uv run poe lint    # ruff check
uv run poe fmt     # ruff format
```

El archivo `.env` se carga automáticamente al iniciar la app (`app/core/config.py`).

## Endpoints

- `GET /api/health` → estado de la API

### Tracking (`/api/tracking`, ver `/docs`)

| Ruta | Para qué |
|---|---|
| `POST /detect` | Detección **paralela** de un lote de frames (multipart: `frames` JPEG, `t` en segundos, `orig_width`, `orig_height`; máx. 24 frames y 4,5 MB por petición). Devuelve `[x1,y1,x2,y2,conf,on_track]` por frame, en píxeles del video original |
| `POST /track` | ByteTrack sin estado sobre las detecciones acumuladas (JSON `frames:[{t, dets}]`) → JSON del contrato |
| `POST /process` | Pipeline **completo** sobre `{"source":"NCCA"}` o `{"blob":"videos/x.mp4"}` (máx. 40 s). Cachea por hash del video |
| `GET /presets/{name}` | Resultado precomputado de un video de ejemplo (`NCCA`) |
| `GET /results/{key}` | Resultado guardado por `/process` |

`/detect` y `/process` gastan créditos de Roboflow: si `DEMO_ACCESS_KEY` está definida exigen el
header `X-Demo-Key`. Las variables `ROBOFLOW_*`, `BLOB_*` y `STORAGE_BACKEND` son opcionales al
arrancar (ver `.env.example`).

**Almacenamiento:** Vercel Blob (`BLOB_STORE_ID` + token OIDC, automático en Vercel) o disco local
en `.cache/storage` si no hay credenciales (`STORAGE_BACKEND=auto`). Para probar Blob en local:
`vercel link` + `vercel env pull`.

**Videos de ejemplo (presets):** `NCCA.mp4` y su `NCCA.tracks.json` no están en git (pesan y
engordan el bundle de Vercel). Viven en el almacenamiento bajo `presets/`. Los archivos locales
van en `app/assets/` (ignorado por git) y se publican con:

```bash
uv run python -m app.cv.publish_presets   # Blob con STORAGE_BACKEND=blob + credenciales, o .cache/storage en local
```

### CLI de depuración

```bash
uv run python -m app.cv.cli --source app/assets/NCCA.mp4   # genera app/assets/out/*.tracks.json y .tracked.mp4 (ambos fuera de git)
```

## Estructura

```
app/
├── main.py          # FastAPI app, lifespan, handlers
├── api/             # routers
├── core/            # config, logger, errores de dominio
├── clients/         # clientes externos (HTTP, almacenamiento Blob/local)
├── cv/              # detección (Roboflow), filtro de pista y ByteTrack
├── dependencies/    # dependencias de FastAPI
├── repositories/    # acceso a datos (stub)
├── schemas/         # modelos Pydantic
├── services/        # lógica de negocio
├── tests/           # tests
└── utils/           # utilidades
```

## Docker

```bash
docker build -t orchestrator .
docker run -p 8080:8080 --env-file .env orchestrator
```
