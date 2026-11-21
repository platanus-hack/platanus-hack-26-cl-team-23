# TRAZADA · posición en tiempo real de cada corredor

Primer módulo del producto: a partir del video de un celular en la tribuna, saber **dónde está
cada atleta en la pista, en metros, en cada frame**. Lo demás (metros extra, decisión táctica,
capa aumentada) se construye encima de esta salida.

```
frame ─► YOLO26 (personas) ─► ByteTrack (ID por persona) ─► punto de apoyo (px)
      ─► homografía px→m ─► coordenadas de pista (s, d) ─► filtro + re-unión de IDs ─► JSON / WebSocket
```

- **s**: metros desde la meta en sentido de carrera, sobre la línea de medición (0–400).
- **d**: metros desde el bordillo; de ahí sale la pista (`lane`) y los metros de más en curva.
- Las personas fuera de la pista (público, jueces en el pasto) se descartan por `d`.

## Instalación

```bash
python3.14 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Usa la GPU de Apple (MPS) automáticamente; CUDA si existe; si no, CPU.

**Datos que no están en el repo** (pesan mucho o son de terceros):
- El video de la final: guardarlo como `data/ncaa1500.mp4` (final 1500 m varones NCAA 2025,
  YouTube `Pp112LRjETs`, 1280×720).
- Los pesos de YOLO (`*.pt`): ultralytics los descarga solos la primera vez.
- `out/`: todo lo generado (calibraciones, features, videos). Las herramientas de TV
  (`tools/fit_broadcast.py`, `tools/refine_gauge.py`) dependen de etiquetas de líneas hechas a
  mano que quedaron fuera; el filtro de zonas (`zone_features`, `eval_zones`, `render_zones`)
  funciona solo con el video y `data/zones_labels.jsonl`.

## Uso

1. **Calibrar** (una vez por posición de la cámara): clic en ≥4 puntos conocidos de la pista
   y escribir su `s d` en la terminal. Con `c` se ven las líneas reproyectadas: tienen que
   calzar con las pintadas.

   ```bash
   .venv/bin/python calibrate.py --source video.mp4 --out calib.json
   ```

2. **Correr**:

   ```bash
   .venv/bin/python run.py --source video.mp4 --calib calib.json --show
   ```

   En vivo: `--source 0` (cámara; un iPhone cercano aparece como cámara vía Continuity Camera)
   o una URL `rtsp://`/`http://` de una app tipo IP Webcam. `--ws 8765` transmite cada frame
   al front; `--jsonl pos.jsonl` lo guarda; `--save out.mp4` graba el video anotado.

Mensaje por frame:

```json
{"t": 4.2, "frame": 126, "runners": [
  {"id": 3, "s": 11.21, "d": 2.91, "lane": 3, "segment": "curva1", "speed": 7.3,
   "extra": 0.62, "rank": 1, "x": 52.9, "y": -38.8, "px": [612, 410], "bbox": [...], "conf": 0.81}]}
```

## Prueba sin ir a la pista

```bash
.venv/bin/python -m tools.make_synthetic          # video con verdad de terreno + puntos de calibración
.venv/bin/python calibrate.py --source out/synth.mp4 --points out/synth_points.json --out out/synth_calib.json
.venv/bin/python run.py --source out/synth.mp4 --calib out/synth_calib.json --jsonl out/synth_pos.jsonl --save out/synth_annotated.mp4
.venv/bin/python -m tools.evaluate out/synth_pos.jsonl out/synth_truth.jsonl
.venv/bin/python -m pytest -q tests
```

Resultado actual (4 corredores, uno adelanta por fuera tapando a otro, 1280×720, M5):
~100 fps, error en `s` y `d` de 2–9 cm (desv.), pista correcta 99–100 %, un cambio de ID en total.
Ojo: es un video sintético con recortes pegados; la cifra real hay que medirla con video de pista.

## Cómo se resuelven los problemas difíciles

| Problema | Solución actual | Siguiente paso |
|---|---|---|
| La caja "respira" con la zancada | Velocidad por regresión sobre 1 s; alfa-beta en (s, d) | Modelo de pose (`--model yolo26n-pose.pt`) usa el tobillo apoyado |
| Corredores que se tapan | Buffer de 2 s en ByteTrack + re-unión de IDs por predicción en metros | Re-ID por color de camiseta / dorsal (OCR) |
| El tracker cambia de persona (swap) | Se suelta el ID si implica un salto físicamente imposible (>0,6 m lateral) | Validar umbrales con video real |
| Público y jueces | Filtro por `d` fuera de la pista | Máscara de zona |
| Retraso en vivo | Hilo lector que entrega solo el último frame | Medir latencia extremo a extremo |

## Archivos

- `trazada/geometry.py` – pista de 400 m: mundo ⇄ (s, d), pista, tramo, metros extra.
- `trazada/calibration.py` – homografía, guardar/cargar, error de reproyección.
- `trazada/pipeline.py` – fuente de video, detector + tracker, re-unión de IDs, `RunnerState`.
- `trazada/filters.py` – suavizado y velocidad por corredor.
- `trazada/viz.py`, `trazada/stream.py` – dibujos de depuración; JSONL y WebSocket.
- `tools/` – video sintético y evaluación contra verdad de terreno.

Geometría nominal (R = 36,5 m, recta 84,39 m, pista 1,22 m): verificar contra la pista donde se grabe.

## Video de TV (experimental)

`data/ncaa1500.mp4` (final 1500 m NCAA 2025, toma 156–163 s). La cámara de TV gira, hace zoom y
probablemente se traslada, así que no sirve una calibración fija.

```bash
.venv/bin/python -m tools.refine_gauge     # calibración inicial afinada con varios frames
.venv/bin/python -m tools.run_broadcast    # -> out/broadcast.mp4 y out/broadcast.jsonl
```

- Calibración inicial: líneas de pista etiquetadas en un frame + homografía ajustada en metros
  (`tools/fit_broadcast.py`, error 1,6 cm sobre las líneas). Ubica la toma en el final de la curva 2.
- Seguimiento de cámara: ECC sobre la imagen de líneas pintadas (`HomographyTracker`). El tartán
  no tiene textura para flujo óptico ni SIFT.
- **Qué funciona:** detección + BoT-SORT con apariencia: 18 IDs para ~13 corredores en 7 s. La
  pista (`lane`) es razonable en toda la toma.
- **Qué no:** `s` y la velocidad solo son confiables ~1,5 s. En la recta, las líneas paralelas no
  dicen cuánto avanzó la cámara siguiendo al grupo, así que la calibración "se desliza" con ellos
  y las velocidades caen a ~1 m/s. La corrección por líneas (`correct=True`) diverge en esta toma.
- Para arreglarlo hace falta una referencia a lo largo de la pista: marcas transversales
  (vallas, relevos), la línea de meta, o restringir con la velocidad física de los corredores.

## ¿En qué zona enfoca la cámara?

Seis zonas en `s`: Z1/Z2 = mitades de la curva 1, Z3 = recta opuesta, Z4/Z5 = mitades de la curva 2,
Z6 = recta principal (termina en la meta). El 1500 parte en s = 100 (Z2) porque toda carrera termina
en la meta (`trazada/zones.py`).

```
frame ─► detector de cortes (trazada/shots.py) ───────────────┐
      ─► memoria de cámaras + curvatura (trazada/evidence.py) ─┼─► filtro de partículas sobre metros
reloj de carrera + salida reglamentaria + ritmo plausible ─────┘   recorridos (zone_filter.py) ─► P(Z1..Z6)
```

Todo es causal (solo presente y pasado):

- **Prior**: salida reglamentaria, ritmo plausible y reloj de carrera.
- **Cortes**: histograma de color fuera de los gráficos de TV. Detecta los 14 cortes de la final
  sin falsos positivos; los paneos no cuentan como corte. Un corte ensancha la posición pero no la
  reinicia: en esta transmisión ningún corte deja de mostrar a la cabeza.
- **Memoria de cámaras**: la TV repite las mismas cámaras en cada vuelta. Cuando el filtro está
  seguro guarda la apariencia (color por bandas + orientación de bordes) con su posición; más
  tarde, si reconoce el encuadre, "recuerda" dónde era. Solo valen recuerdos de hace más de 40 s
  (de la vuelta anterior) y con distancia absoluta < 0,75; si no, no opina. No usa etiquetas.
- **Curvatura**: las rectas se ven rectas desde cualquier punto de vista; las curvas, curvas.
  Flecha/cuerda de cada línea pintada, con peso según cuánta línea se ve. Evidencia débil
  (AUC 0,76): los teleobjetivos aplanan las curvas.

```bash
.venv/bin/python -m tools.zone_features                    # una pasada por el video (~30 s)
.venv/bin/python -m tools.eval_zones data/zones_labels.jsonl --features out/zone_feats.npz --ablation
.venv/bin/python -m tools.label_zones                      # revisar / corregir etiquetas
```

Resultado (final 1500 NCAA 2025, 455 muestras cada 0,5 s, promedio de 3 semillas, cortes detectados):

| Evidencia | Exactitud | 0–60 s | 60–120 s | 120–180 s | 180–227 s |
|---|---|---|---|---|---|
| Solo prior | 55 % | 90 % | 44 % | 41 % | 42 % |
| + curvatura | 69 % | 92 % | 91 % | 54 % | 31 % |
| + memoria de cámaras | 82 % | 90 % | 89 % | 77 % | 67 % |
| + ambas | **86,5 %** | 92 % | 90 % | 82 % | 81 % |

- Lejos de los límites entre zonas: 92 %. Todos los errores son la zona vecina, casi siempre
  por atraso (la histéresis confirma un cambio en ~1,5 s). Error mediano en `s`: 10 m.
- La memoria reconoce el encuadre en ~50 % de las muestras; en el resto manda el prior.
- `data/zones_labels.jsonl` es un **borrador**: zona de la cabeza de carrera interpolada entre anclas
  leídas del video (reloj de los 200 m, cartel-reloj de salida de curva 2, contador de vueltas,
  llegada 3:47,27; ±1 s), con los 14 cortes. Revisarlo a mano con `label_zones`.
- La carrera parte en el segundo 58,7 del video; el reloj del gráfico es exactamente `t − 58,7`.
- Ojo, sesgo: los umbrales (curvatura, distancia de reconocimiento) se eligieron con este mismo
  video, en su mayoría mirando solo la vuelta 1. Falta probar con otra carrera.

Video con el pronóstico impreso (calculado en línea, sin mirar el futuro):

```bash
.venv/bin/python -m tools.render_zones --labels data/zones_labels.jsonl --out out/zonas_raw.mp4
avconvert -p Preset1280x720 -s out/zonas_raw.mp4 -o out/zonas.mp4
```
