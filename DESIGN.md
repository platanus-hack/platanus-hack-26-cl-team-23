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

**"Carriles": una T hecha de carriles.** Una barra arriba y tres carriles que bajan; los dos de los costados nacen de la barra con una curva, como una pista que dobla. Monocroma en tinta `#1D1D1F`, a propósito: el naranja queda reservado para el dato protagonista y no compite con la marca en cada pantalla.

```svg
<svg viewBox="0 0 40 40" fill="none" stroke="#1D1D1F" stroke-width="3.6" stroke-linecap="round" xmlns="http://www.w3.org/2000/svg">
  <path d="M4 6 H36"/>
  <path d="M4 13 H8 A6 6 0 0 1 14 19 V36"/>
  <path d="M36 13 H32 A6 6 0 0 0 26 19 V36"/>
  <path d="M20 13 V36"/>
</svg>
```

- Junto al nombre **"Trazada"** (SF Pro Display / Inter, peso 600, interletra −0,02 em), con la marca a la izquierda.
- Sobre fondo oscuro, el trazo pasa a blanco. En código, la marca usa `currentColor` y toma el color del texto que la rodea.
- Archivo fuente: `research/pitch/logo/trazada-marca.svg`. En la app: `TrackMark` (`frontend/spa/src/components/trazada/ui.tsx`) y `frontend/spa/public/favicon.svg`.
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

- Degradados morados o azules genéricos, brillos, neón, acentos que brillan sobre fondo oscuro (el modo oscuro de la sección 9 es sobrio: mismos colores, sin brillo).
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

## 9. Modo oscuro

**Para qué:** presentar. En la pantalla del escenario y al compartir pantalla, el blanco se sobresatura y "quema" la imagen; el negro no. Es el mismo sistema "Pista" con otros valores para los mismos tokens: las reglas de color no cambian (naranja solo para el protagonista, verde/rojo solo para ganó/perdió, todo lo demás en grises, el cielo solo en sus dos lugares).

**Cómo se activa** (en orden de prioridad):
1. `?tema=oscuro` o `?tema=claro` en la URL. **Para el escenario: abrir la app con `?tema=oscuro`.**
2. El botón sol/luna del header, que recuerda la elección.
3. Lo que pide el sistema operativo.

En código: `data-theme="dark"` en `<html>`, el bloque `:root[data-theme="dark"]` de `frontend/spa/src/index.css` y `src/trazada/theme.ts`. Un script en `index.html` aplica el tema antes de pintar, para que no parpadee en blanco. Los dibujos en canvas (cámara y vista cenital) vuelven a leer los colores y se redibujan al cambiar.

| Token | Claro | Oscuro | Nota |
|---|---|---|---|
| Fondo (`bg`) | `#F5F5F7` | `#000000` | El proyector no emite luz: no satura |
| Superficie (`surface`) | `#FFFFFF` | `#1C1C1E` | Secciones |
| Zona secundaria (`paper2`) | `#F5F5F7` | `#2C2C2E` | Bloques de cifra |
| Línea (`line`) | `#E5E5EA` | `#38383A` | |
| Tinta (`fg`) | `#1D1D1F` | `#F2F2F4` | Casi blanco, nunca `#FFF` puro en superficies grandes (15:1) |
| Tinta suave (`muted`) | `#6E6E73` | `#A1A1A6` | 6,6:1 sobre superficie |
| Naranja protagonista (`pick`) | `#FF5B14` | `#FF5B14` | No cambia |
| Naranja como texto (`hero`) | `#C2410C` | `#FF8A50` | Sobre oscuro se aclara (7,3:1) |
| Franja de costo (`band`) | `#FFD8C4` | `#4A2414` | Tinte oscuro, no claro |
| Resto de corredores (`other`) | `#8E8E93` | `#8E8E93` | |
| Ganó (`gain`) | `#1A7F37` | `#30D158` | |
| Perdió (`loss`) | `#D70015` | `#FF453A` | |
| Acción (`accent`) | `#0071E3` | `#0071E3` | Igual en ambos: con `#0A84FF` el texto blanco del botón queda en 3,6:1 y no pasa AA |
| Carriles (alternados) | `#E8E8ED` / `#DEDEE3` | `#232326` / `#2A2A2D` | |
| Líneas de pista (`trackline`) | `#FFFFFF` | `#48484C` | Más claras que los carriles, sin brillar |
| Pasto (`grass`) | `#F5F5F7` | `#111113` | |

- **Vidrio esmerilado:** `rgba(28, 28, 30, .72)` con el mismo desenfoque, texto claro.
- **Cielo con grano:** atardecer nocturno, grano al 25 %:
  `radial-gradient(120% 90% at 50% 115%, #FF5B14 0%, #B8461E 20%, #4A2638 44%, #1B1A33 70%, #08080F 100%)`. Sobre él, texto claro.
- **Logo:** `currentColor`, pasa a claro solo.
- Sobre el naranja, el texto sigue en tinta oscura `#1D1D1F`, también en modo oscuro.
- Las capas dibujadas sobre el video no cambian: el video ya es oscuro.
