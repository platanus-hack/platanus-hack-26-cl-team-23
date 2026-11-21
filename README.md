<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./docs/assets/trazada-for-dark.svg">
  <img src="./docs/assets/trazada-for-light.svg" alt="TRAZADA" height="72">
</picture>

# TRAZADA

**Mide lo que el cronómetro no ve.**

Sigue a cada corredor en un video de pista y calcula cuántos metros de más corre quien va por fuera en la curva.

<img src="https://img.shields.io/badge/Platanus%20Hack-26%20Santiago-F0FF00?style=for-the-badge&labelColor=1A1A1A" alt="Platanus Hack 26 Santiago" />
<img src="https://img.shields.io/badge/Track-%F0%9F%8C%8E%20Physical%20World-1D1D1F?style=for-the-badge" alt="Track Physical World" />
<img src="https://img.shields.io/badge/team-23-3B5BDB?style=for-the-badge" alt="team-23" />

<br />

<img src="./project-logo.png" alt="Platanus Hack 26 Santiago" width="160" />

<br /><br />

[**Ver la demo**](https://platanus-hack-26-nid.vercel.app) · [Cómo funciona](#cómo-funciona) · [Infraestructura](#infraestructura) · [Desarrollo](#desarrollo)

</div>

---

## El problema

En una carrera de 400 m el cronómetro da un tiempo, pero no cuenta **cómo se corrió**. Quien va por un carril exterior o se abre en la curva recorre más metros que quien va pegado a la cuerda, y eso casi nunca se ve en una transmisión.

## Qué hace

| | |
|---|---|
| 🎯 **Seguimiento** | Detecta a cada atleta en el video y le asigna un id estable durante toda la carrera. |
| 🗺️ **Vista cenital** | Ubica a cada corredor en una pista de 400 m vista desde arriba, con sus ocho carriles. |
| 📷 **Zona de cámara** | Indica qué tramo de la pista enfoca la cámara en cada cuadro. |
| 🎙️ **Relato con voz** | Narra la carrera por tramos. El guion no puede inventar: toda cifra se verifica contra los datos medidos antes de sintetizar el audio. |

## Así se ve

<div align="center">
  <img src="./docs/assets/screens/seguimiento.jpg" alt="TRAZADA: video con cada corredor detectado, su id y la lista de atletas" width="880" />
  <p><sub>Seguimiento: cada corredor con su id estable, en pantalla y en la lista de atletas.</sub></p>
  <br />
  <img src="./docs/assets/screens/analisis.png" alt="TRAZADA: relato de la carrera, pista de 400 m y ficha del corredor" width="880" />
  <p><sub>Relato de la carrera, ubicación sobre la pista de 400 m y ficha del corredor.</sub></p>
</div>

## Cómo funciona

<div align="center">
  <img src="./docs/assets/flow.svg" alt="Flujo de TRAZADA: del video al relato con voz" width="760" />
</div>

1. **El navegador** saca cuadros a 10 fps y envía solo esos, no el video completo.
2. **El backend** detecta y sigue a los corredores (ByteTrack) y estima la zona de pista que ve la cámara.
3. Con eso arma **los hechos** de la carrera, escribe el relato con Claude y lo narra con ElevenLabs.
4. **La interfaz** muestra el video con las cajas, la lista de corredores, la vista cenital y el relato sincronizado con el play.

> El diagrama está en [`docs/flow.d2`](./docs/flow.d2). Para regenerarlo: `make docs`.

## Infraestructura

<div align="center">
  <img src="./docs/assets/infra.svg" alt="Infraestructura: Vercel Services, GCP y APIs externas" width="760" />
</div>

## Hecho con

<div align="center">

<img src="https://img.shields.io/badge/React-19-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React" />
<img src="https://img.shields.io/badge/Vite-8-646CFF?style=for-the-badge&logo=vite&logoColor=white" alt="Vite" />
<img src="https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript" />
<img src="https://img.shields.io/badge/Tailwind-4-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white" alt="Tailwind CSS" />
<img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
<img src="https://img.shields.io/badge/Python-3.13-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
<img src="https://img.shields.io/badge/Terraform-844FBA?style=for-the-badge&logo=terraform&logoColor=white" alt="Terraform" />

<br /><br />

<a href="https://hack.platan.us"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="./docs/assets/platanus-for-dark.svg">
  <img src="./docs/assets/platanus-for-light.svg" alt="Platanus" height="28">
</picture></a>
&nbsp;&nbsp;&nbsp;&nbsp;
<a href="https://www.anthropic.com"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="./docs/assets/anthropic-for-dark.svg">
  <img src="./docs/assets/anthropic-for-light.svg" alt="Anthropic" height="22">
</picture></a>
&nbsp;&nbsp;&nbsp;&nbsp;
<a href="https://elevenlabs.io"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="./docs/assets/elevenlabs-for-dark.svg">
  <img src="./docs/assets/elevenlabs-for-light.svg" alt="ElevenLabs" height="22">
</picture></a>
&nbsp;&nbsp;&nbsp;&nbsp;
<a href="https://vercel.com"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="./docs/assets/vercel-for-dark.svg">
  <img src="./docs/assets/vercel-for-light.svg" alt="Vercel" height="20">
</picture></a>

</div>

## Equipo

**team-23** · Platanus Hack 26 Santiago

| | |
|---|---|
| Daniel Acuña Ureta | [@danielauu](https://github.com/danielauu) |
| Nicolás Cruzat | [@nicru](https://github.com/nicru) |
| Andrés Ignacio Sebastian De La Fuente | [@AndresSebad](https://github.com/AndresSebad) |

---

# Documentación técnica

Monorepo de un frontend SPA (React + Vite + TypeScript) y un backend FastAPI,
desplegables juntos en Vercel Services o por separado en GCP.

## Stack

| Parte | Tecnología |
|---|---|
| `frontend/spa` | React 19, Vite 8, TypeScript, Tailwind CSS 4, React Router 8, Bun |
| `backend/orchestrator` | FastAPI, Pydantic, Granian, uv, Python 3.13 |
| Deploy | Vercel Services · Terraform (Cloud Run + App Engine) |

## Estructura

```
.
├── frontend/spa/               # SPA (Vite)
│   └── src/
│       ├── components/trazada/ # video, lista de corredores, vista cenital
│       ├── lib/                # cliente de la API + query client
│       ├── pages/
│       ├── trazada/            # subida, zonas, adaptador y modelo de dibujo
│       └── types/              # api.gen.ts (generado del OpenAPI)
├── backend/orchestrator/       # API (FastAPI)
│   └── app/
│       ├── api/                # routers
│       ├── core/               # config, logger, domain errors
│       ├── clients/            # clientes HTTP
│       ├── dependencies/       # dependencias FastAPI
│       ├── repositories/       # acceso a datos (stub)
│       ├── schemas/            # modelos Pydantic
│       ├── services/           # lógica de negocio
│       ├── tests/              # tests
│       └── utils/
├── deployment/gcp/terraform/   # Cloud Run + App Engine
├── vercel.json                 # Vercel Services (spa + orchestrator)
├── Makefile
└── platanus-hack-26.code-workspace
```

## Requisitos

- [Bun](https://bun.sh/) ≥ 1.4
- [uv](https://docs.astral.sh/uv/) ≥ 0.7
- Python 3.13 (lo gestiona uv)
- Opcional: Terraform ≥ 1.5, Vercel CLI

## Setup

```bash
make install

# El backend exige todas las variables de entorno
cp backend/orchestrator/.env.example backend/orchestrator/.env
```

## Desarrollo

```bash
make dev                                                  # spa + orchestrator
# o por separado:
cd frontend/spa && bun run dev                            # http://localhost:5173
cd backend/orchestrator && uv run poe dev                 # http://localhost:8080
```

- Frontend: http://localhost:5173
- API: http://localhost:8080/api/health
- El frontend llama al backend con rutas relativas (`/api/...`); Vite las proxya a `:8080`.

## Comandos (`make help`)

| Comando | Descripción |
|---|---|
| `make install` | Instala dependencias de spa y orchestrator |
| `make dev` | Levanta ambos en paralelo |
| `make test` | Tests del backend |
| `make lint` | Ruff |
| `make fmt` | Ruff format |
| `make types` | Regenera los tipos TS del spa desde el OpenAPI del backend |
| `make reqs` | Regenera `requirements.txt` para Vercel |
| `make vercel-dev` | `vercel dev` |
| `make deploy` | `vercel --prod` |
| `make docs` | Regenera los diagramas D2 (`docs/*.d2` → `docs/assets/*.svg`) |

## Integración front ↔ back

El contrato lo manda el backend: `make types` vuelca su OpenAPI a
`backend/orchestrator/openapi.json` y genera `frontend/spa/src/types/api.gen.ts`. El front no
escribe tipos de la API a mano; si un esquema de Pydantic cambia, el build del spa falla.
`src/trazada/adapter.ts` es la única frontera entre esos tipos y el modelo de dibujo (`Race`).

Al subir un video, el navegador no sube el archivo: saca cuadros a 10 fps y manda solo esos.

```
extraer cuadros (10 fps, JPEG ≤960 px)
  ├─ lotes de 24 ─► POST /api/tracking/detect   (cajas, en píxeles del video original)
  └─ mismos lotes ─► POST /api/zones/features   (evidencia visual del encuadre)
POST /api/tracking/track   ─► ids estables por corredor (ByteTrack)
POST /api/zones/           ─► zona Z1..Z6 que enfoca la cámara en cada cuadro
```

Los dos resultados se unen por el número de cuadro (`frames[].frame`, la posición en la lista
enviada). Hasta tres lotes viajan en paralelo; si las zonas fallan, la carrera se arma igual
con el seguimiento. `app/tests/test_frontend_contract.py` verifica esa cadena completa.

La pantalla muestra **solo lo que devuelven esos endpoints**: el video con las cajas y el id
de cada corredor, la lista de corredores seguidos con sus tiempos y su `on_track`, y la vista
cenital con el tramo de pista que enfoca la cámara. No hay datos de ejemplo ni simulaciones:
sin video subido no hay nada que mostrar.

El backend además guarda resultados precomputados (`GET /api/tracking/presets/{name}`,
`POST /api/tracking/process`, `uv run python -m app.cv.publish_presets`), pero el front no
los consume.

Lo que todavía no existe es la geometría por corredor (metros sobre la pista, distancia a la
cuerda, metros extra en la curva): hace falta la homografía por cuadro, que vive en
`research/trazada` y aún no tiene endpoint. Hasta entonces no se dibuja nada de eso.

## Relato de la carrera

`POST /api/narration/` recibe lo que ya devolvieron `/tracking/track` y `/zones/` y devuelve
el relato: texto por tramos, con la duración real de cada audio.

```
tracks + zones ─► hechos (cv/race_facts.py)  ← resumen determinista, sin IA
                ─► guion (Claude)            ← tool use obligado: JSON garantizado
                ─► validación                ← cifras, léxico y cobertura
                ─► voz (ElevenLabs)          ← una petición por tramo
```

El guion **no puede inventar**. Antes de sintetizar nada se verifica que toda cifra exista en
los hechos y que no se afirme nada que el sistema no mide (puestos, quién gana, tiempos). Si
el guion no pasa, se reintenta una vez con el error a la vista; si vuelve a fallar, o si no
hay claves configuradas, se usan plantillas deterministas. La demo nunca se queda muda.

Sin posiciones por corredor el relato habla de lo que sí hay: cuántos atletas se siguen,
cuántos caben en cuadro, cuándo aparece o se pierde uno, qué tramo enfoca la cámara y cuántos
cambios de plano hay. El `disclaimer` de la respuesta dice explícitamente qué no mide.

La voz va enganchada al play del video: cada tramo suena dentro de su ventana, se pausa con
el video y salta con la línea de tiempo. Como el largo del texto no se puede pedir con
precisión a un modelo, el backend mide la duración real de cada mp3 y, si algún tramo se pasa
de su ventana, pide **un** recorte con esa cifra en la mano. Además el front acelera hasta
1,35× para encajar el tramo, antes que cortar una frase a la mitad.

Se usa `eleven_v4`, que habla más rápido que Multilingual v2 y por eso cabe mejor en clips
cortos.

El mismo video produce la misma clave de caché: repetir la demo no gasta cuota de Claude ni
de ElevenLabs. `GET /api/narration/{key}/audio/{i}` sirve el mp3 de cada tramo.

## Variables de entorno

El backend no tiene defaults para lo esencial: `APP_ENV`, `APP_HOST`, `APP_PORT` y
`HTTP_TIMEOUT` son obligatorias. El resto es opcional y degrada con elegancia:

| Variable | Si falta |
|---|---|
| `ROBOFLOW_API_KEY` | `/detect` y `/process` responden 502 |
| `ANTHROPIC_API_KEY` | el relato se arma con plantillas |
| `ELEVEN_LABS_API_KEY` | el relato vuelve solo como texto |
| credenciales de Blob | el almacenamiento cae a disco local |

Ver `backend/orchestrator/.env.example`.

## Deploy en Vercel

`vercel.json` declara dos services y el ruteo:

- `/api/*` → `orchestrator` (FastAPI)
- `/*` → `spa` (React)

El deploy se puede lanzar manualmente vía el workflow
`.github/workflows/deploy-vercel.yml` (Actions → Deploy Vercel → Run workflow) o por CLI:

| Rama origen | `environment` | Despliega |
|---|---|---|
| `dev` | `preview` | `dev` |
| `main` | `production` | `main` |

Cualquier otra combinación falla en el paso de validación.

```bash
# preview desde dev
gh workflow run deploy-vercel.yml --ref dev -f environment=preview

# production desde main
gh workflow run deploy-vercel.yml --ref main -f environment=production
```

O por CLI de Vercel:

```bash
vercel link        # Root Directory = raíz del repo
make reqs          # mantiene requirements.txt al día
make deploy
```

<details>
<summary><b>⚠️ Deploying & integrations (Vercel, Render, etc.)</b></summary>

Deploy platforms like **Vercel**, **Render** or **Netlify** can only connect to
repositories **you own** — they can't be granted access to this organization repo.
To deploy (or add any integration) while keeping your commits here, mirror your
code to a personal repo:

1. Create a **personal** repository on your own GitHub account.
2. Point your local `origin` at **both** repos, so a single `git push` updates each one:

   ```bash
   # this org repo (keep it as a push target)...
   git remote set-url --add --push origin https://github.com/platanus-hack/platanus-hack-26-cl-team-23.git
   # ...and your personal repo
   git remote set-url --add --push origin https://github.com/<your-user>/<your-repo>.git
   ```

   From now on `git push` sends every commit to **both** repositories.
3. Connect your deploy service (Vercel, Render, …) to your **personal** repo and deploy from there.

Your commits stay mirrored here for judging, while the deploy runs from the repo you control.

</details>

## Deploy en GCP

```bash
cd deployment/gcp/terraform
terraform init
terraform plan
terraform apply
```

Provisiona Cloud Run (mínimos: 128Mi, 0–1 instancias) y App Engine Standard
(F1, 0–1 idle instances). Requiere `gcloud` autenticado por el `data external`
que resuelve la imagen a digest.

## Tests y calidad

```bash
make test   # pytest
make lint   # ruff
```

## VS Code

Abrir el workspace con `spa` y `orchestrator` como raíces:

```bash
code platanus-hack-26.code-workspace
```
