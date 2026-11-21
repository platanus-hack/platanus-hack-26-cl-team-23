# TRAZADA · Sistema de diseño "Pista"

Guía para cualquier persona o agente que produzca piezas de TRAZADA (app, deck, afiches).
Fuente de verdad en código: `frontend/spa/src/index.css`. Si algo aquí no calza con ese archivo, manda el archivo.

**En una línea:** disciplina suiza con materiales de Apple. Grilla estricta, mucho aire, la tipografía es la protagonista y **el color es información, nunca adorno**.

TRAZADA mide lo que el cronómetro no ve: sigue a cada corredor en un video y lo ubica en la pista (los metros extra que corre por ir por fuera en la curva).

---

## 1. Color

### Reglas (lo más importante de este documento)

1. **Naranja = el protagonista.** El corredor elegido o el dato principal de la lámina. Uno por pantalla. Nunca decorativo.
2. **Verde / rojo = ganó / perdió** (puestos, ventaja). Solo cuando ese dato existe.
3. **Azul = acción** (botones, enlaces). En un deck casi no aparece.
4. **Todo lo demás en grises.**
5. El **cielo con grano** es el único gesto expresivo: máximo en portada y cierre, nunca detrás de datos.

### Paleta

| Rol | Hex | Uso |
|---|---|---|
| Fondo | `#F5F5F7` | Fondo de página o lámina |
| Superficie | `#FFFFFF` | Tarjetas |
| Zona secundaria | `#F5F5F7` | Bloques de cifra dentro de una tarjeta |
| Línea | `#E5E5EA` | Divisiones |
| Tinta | `#1D1D1F` | Texto principal, cifras |
| Tinta suave | `#6E6E73` | Texto secundario, rótulos (5,1:1 sobre blanco) |
| **Naranja (protagonista)** | `#FF5B14` | Trazos, marcas, bloques del dato principal |
| Naranja como texto | `#C2410C` | Cuando el naranja va en texto chico (5,2:1) |
| Franja de costo | `#FFD8C4` | Fondo suave del dato protagonista, área de "costo" en gráficos |
| Resto de corredores | `#8E8E93` | Líneas y puntos secundarios |
| Ganó | `#1A7F37` | ▲ puestos ganados |
| Perdió | `#D70015` | ▼ puestos perdidos |
| Acción | `#0071E3` | Botones, enlaces |

Sobre el naranja `#FF5B14` el texto va en **tinta `#1D1D1F`** (5,6:1), nunca en blanco (3,1:1, no se lee).

### Cielo con grano

Degradado radial de atardecer, con ruido fino encima (opacidad ~35 %, modo *overlay*):

```
radial-gradient(120% 90% at 50% 115%,
  #FF5B14 0%, #FFA36B 32%, #F6C9A8 50%, #B9B8E6 74%, #8E9BE0 100%)
```

El naranja nace abajo y sube a lavanda/azul. Sobre el cielo, el texto va en tinta.

---

## 2. Tipografía

- **Titulares y cifras:** SF Pro Display (Apple). Si no está, **Inter**.
- **Texto:** SF Pro Text / Inter.
- **Rótulos y medidas:** **Geist Mono**, MAYÚSCULAS, espaciado +0,08 em, peso 500.

| Rol | App | Deck (1920×1080) | Peso | Interletra |
|---|---|---|---|---|
| Cifra protagonista | 96 px | 200–280 px | 700 | −0,04 em |
| Titular | 64 px | 96–120 px | 700 | −0,035 em |
| Título de sección | 20 px | 40–48 px | 600 | −0,015 em |
| Texto | 16 px | 28–32 px | 400 | 0 |
| Rótulo (mono, mayúsculas) | 11 px | 18–22 px | 500 | +0,08 em |

Escala cerrada de la app: **12 · 14 · 16 · 20 · 24 · 32 · 48 · 64 · 96**. No inventes tamaños intermedios.

Reglas:
- Titulares en **oración normal** (no todo en mayúsculas). Las mayúsculas son solo para rótulos mono.
- Cifras con números tabulares, coma decimal chilena: `+3,2 m`, `0,50 s`.
- La jerarquía la dan **tamaño y peso**, no el color.

---

## 3. Composición

- **Mucho aire.** Una idea por lámina.
- **Tarjetas blancas** sobre fondo `#F5F5F7`, radio **22 px** (bloques internos 14 px). Sin bordes ni sombras.
- **Grilla de 12 columnas**, márgenes generosos (≥ 96 px en deck), separación entre tarjetas de 20 px (app) o 32 px (deck).
- Alineación a la izquierda. Nada centrado salvo la portada.
- El dato manda: la cifra grande primero, la explicación después, la fuente al final en rótulo mono.

**Vidrio esmerilado** (blanco al 72 % + desenfoque) solo cuando algo flota sobre una imagen o un video, como un rótulo encima del video de la carrera.

---

## 4. Logo

La curva de una pista vista desde arriba: tres carriles concéntricos en forma de "D". Los dos interiores en tinta y **el exterior en naranja**, porque ir por fuera es lo que medimos.

```svg
<svg viewBox="0 0 40 40" fill="none" stroke-linecap="round" stroke-width="3.4" xmlns="http://www.w3.org/2000/svg">
  <path d="M4 14.5 H17 A5.5 5.5 0 0 1 17 25.5 H4" stroke="#1D1D1F"/>
  <path d="M4 9.5 H17 A10.5 10.5 0 0 1 17 30.5 H4" stroke="#1D1D1F"/>
  <path d="M4 4.5 H17 A15.5 15.5 0 0 1 17 35.5 H4" stroke="#FF5B14"/>
</svg>
```

- Junto al nombre **"Trazada"** (SF Pro / Inter, peso 600, interletra −0,02 em), con la marca a la izquierda.
- Sobre fondo oscuro, los carriles interiores pasan a blanco; el exterior sigue en naranja.
- No rotar, no deformar, no agregar sombras ni degradados.

---

## 5. Gráficos y datos

- Línea del protagonista: naranja `#FF5B14`, 3 px. Resto: gris `#8E8E93`, 1–1,5 px.
- Referencia ideal ("si hubiera ido por la cuerda"): tinta punteada.
- Costo entre ambas: área `#FFD8C4`.
- Curvas de la pista: zona `#F5F5F7` con rótulo "curva".
- Rótulos de ejes y anotaciones en Geist Mono, gris.
- Nunca diferenciar corredores **solo** por color: usa etiqueta, dorsal o posición.

---

## 6. Recetas de láminas (deck)

1. **Portada:** cielo con grano a pantalla completa, logo + "Trazada" arriba a la izquierda, titular grande en tinta: *"Mira la carrera que el cronómetro no ve."*
2. **El problema:** fondo `#F5F5F7`, una cifra gigante en tinta (por ejemplo `+10,3 m`), una frase debajo y la fuente en rótulo mono.
3. **La cifra protagonista:** tarjeta blanca; `+3,2 m` enorme en tinta; debajo, en dos bloques grises: "Puesto 5.º → 3.º" (▲ 2 en verde) y "Le costó 0,50 s".
4. **Cómo funciona:** tres pasos en tres tarjetas blancas iguales, cada una con un número grande en gris y una frase corta.
5. **Demo:** captura de la app a sangre o dentro de una tarjeta blanca grande, con un rótulo mono que diga qué mirar.
6. **Cierre:** cielo con grano otra vez, logo grande y una sola frase.

---

## 7. No hacer

- Degradados morados o azules genéricos, brillos, neón, fondos oscuros con un acento que brilla.
- Íconos o ilustraciones de stock, emojis como íconos.
- Color decorativo (bloques oliva, beige, etc. sin significado).
- Líneas verticales para "tabular" textos, rótulos sobre cada título (*eyebrows*), numeración 01/02/03 decorativa.
- Más de un naranja protagonista por lámina.
- Titulares en mayúsculas o en mono.
- Texto blanco sobre naranja.

---

## 8. Voz

Español chileno, directo y deportivo. Frases cortas. Primero el valor, después lo técnico. Las cifras siempre con unidad y coma decimal (`0,41 m`, `20,7 s`). Las afirmaciones van con su fuente (por ejemplo *González-Mohíno et al., 2021*).

---

## 9. Overlays sobre video

Lo que dibujamos encima del video de la carrera (cajas, estelas, paneles) sigue las mismas reglas que la app. El video ya trae mucho color y gráficos de la transmisión; nosotros sumamos **lo mínimo, en blanco y un solo naranja**.

Código: `backend/orchestrator/app/cv/theme.py` (OpenCV + Pillow). Muestra: `python -m app.cv.demo_theme --video NCCA.mp4 --tracks NCCA.tracks.json --out despues.png`.

### Qué se dibuja y cómo

| Pieza | Función | Estilo |
|---|---|---|
| Caja del corredor | `corners()` | Cuatro esquinas finas, no un rectángulo cerrado (tapa menos). Blanco 80 %, 2 px. El elegido: naranja `#FF5B14`, 3 px. |
| Etiqueta | `pill()` | Píldora blanca con número en tinta (Geist Mono). El elegido: píldora naranja con texto en tinta, `#7`. **Nunca texto blanco sobre naranja.** |
| Estela de los pies | `trail()` | Elegido: naranja 4 px, uniones redondeadas. Resto: blanco 50 %, 2 px. La cola se desvanece. |
| Panel de datos | `glass_panel()` | Vidrio esmerilado: desenfoque del video + blanco 72 %, radio 22 px. **Nunca paneles negros opacos.** Texto en tinta. |
| Texto | `text()` | Inter / Geist Mono reales con antialias. **Nunca fuentes Hershey de OpenCV.** Rótulos en mono MAYÚSCULAS; unidades siempre en minúscula (`m`, `s`). |
| Vista cenital | `oval()` | Igual que la app: carriles grises alternados `#E8E8ED` / `#DEDEE3`, líneas blancas, zona actual en tinta, incertidumbre como tramo `#FFD8C4` y el punto naranja. |

Color: un corredor elegido en naranja, todos los demás en blanco. Nada de un color por atleta ni un color por zona (paleta arcoíris): no se lee y compite con las camisetas. Verde `#1A7F37` y rojo `#D70015` solo si el dato es ganó / perdió puestos. Como el color no basta para distinguir corredores, cada uno lleva su número.

### Tamaños: por alto del video

Todo se diseña a 1080p y se escala con `Scale(alto)`: `sc.px(22)` mide 22 px en 1080p, 15 px en 720p y 44 px en 4K. Así un render en 720p se ve igual que en 1080p.

| Rol | 1080p | Fuente |
|---|---|---|
| Rótulo | 22 px (mínimo legible) | Geist Mono 500, +0,08 em |
| Texto | 26 px | Inter 400 |
| Título de panel | 36 px | Inter 600 |
| Cifra | 56 px | Inter Display 700, números tabulares |

Ningún texto bajo 22 px a 1080p: el video se mira en celular o proyectado.

### Zona segura

Las transmisiones ponen arriba el logo y el nombre del evento, y abajo el reloj de carrera, los zócalos y el ticker. `safe_rect()` deja libre 8 % arriba, 22 % abajo y 4 % a los lados; los paneles van **dentro** de esa zona (por defecto, abajo a la derecha, justo encima del reloj). Si un video trae gráficos en otro lado, se ajustan los márgenes, no se tapan.

### Movimiento

- **Fundidos cortos:** todo aparece y desaparece en 200 ms (`fade()`), nada salta de golpe. Cuando hay un corte de cámara, las cajas y estelas se borran y vuelven con fundido.
- **Suavizado causal:** `Smoother` suaviza cajas, estelas y cifras usando solo lo que ya pasó (sirve en vivo). Quita el temblor sin "adivinar" el futuro.
- **Cifras que no bailan:** los números van con ancho tabular (`tabular=True`) para que `312 m` → `313 m` no mueva el texto.

### Para migrar un script

1. `from app.cv import theme as th` y `sc = th.Scale(frame.shape[0])` una vez por video.
2. Reemplazar `cv2.rectangle` de cajas por `th.corners(...)`, `cv2.putText` por `th.text(...)` o `th.pill(...)`, `cv2.polylines` de estelas por `th.trail(...)`.
3. Reemplazar paneles negros (`np.zeros` + `addWeighted`) por `th.glass_panel(...)` y escribir encima con `th.text(...)`.
4. Borrar las paletas por id (`id_color`, `_color`, `COLS`): el elegido es naranja y el resto blanco.
5. Cifras con `th.fmt_num()`: coma decimal, punto de miles, unidad en minúscula (`+3,2 m`, `1.188 m`).
