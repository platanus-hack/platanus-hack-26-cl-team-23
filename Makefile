SHELL := /bin/bash

.PHONY: help install dev test lint fmt types reqs vercel-dev deploy

help: ## Mostrar comandos disponibles
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Instalar dependencias del spa y del orchestrator
	cd frontend/spa && bun install
	cd backend/orchestrator && uv sync

dev: ## Correr spa + orchestrator en paralelo
	@echo "Levantando spa (:5173) y orchestrator (:8080)... Ctrl+C para detener."
	@trap 'kill 0' INT TERM EXIT; \
		(cd frontend/spa && bun run dev) & \
		(cd backend/orchestrator && uv run poe dev) & \
		wait

test: ## Tests del orchestrator
	cd backend/orchestrator && uv run poe test

lint: ## Lint del orchestrator
	cd backend/orchestrator && uv run poe lint

fmt: ## Formatear el orchestrator
	cd backend/orchestrator && uv run poe fmt

types: ## Regenerar los tipos TS del spa desde el OpenAPI del orchestrator
	cd backend/orchestrator && uv run poe openapi > openapi.json
	@# se corre desde la raíz a propósito: el spa usa TypeScript 7 y openapi-typescript
	@# necesita la API de factory de TypeScript 5.
	bunx openapi-typescript backend/orchestrator/openapi.json -o frontend/spa/src/types/api.gen.ts

reqs: ## Regenerar requirements.txt para Vercel
	cd backend/orchestrator && uv export --no-dev --no-hashes \
		--format requirements-txt --output-file requirements.txt

vercel-dev: ## Correr todo con Vercel Services en local
	vercel dev

deploy: ## Deploy a producción en Vercel
	vercel --prod
