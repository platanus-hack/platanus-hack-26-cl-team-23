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

## Estructura

```
app/
├── main.py          # FastAPI app, lifespan, handlers
├── api/             # routers
├── core/            # config, logger, errores de dominio
├── clients/         # clientes HTTP externos
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
