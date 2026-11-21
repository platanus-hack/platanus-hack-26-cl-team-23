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
