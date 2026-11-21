ARG BASE_IMAGE=python:3.13-slim
FROM ${BASE_IMAGE}

COPY --from=ghcr.io/astral-sh/uv:0.7.13 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /api

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --group server --no-install-project

COPY app ./app

EXPOSE 8080

CMD ["uv", "run", "--no-dev", "--group", "server", "granian", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8080", "app.main:app"]
