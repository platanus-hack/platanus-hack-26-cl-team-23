# TRAZADA · Guion del pitch (3:00) · v3, base para intervenir

> Base para que el equipo la reescriba con su voz. Lo que va entre **[corchetes]** lo completa Andrés con datos reales. Si algo no es cierto, se cambia o se borra: un jurado nota una anécdota inventada.
> La versión anterior (gancho con Río, bloque "Cómo lo hicimos" aparte) quedó en `guion-v2.md`.

Presenta: **Andrés** · Demo en el teclado: **Nico** · Preguntas técnicas: **Daniel** (las preguntas van fuera de los 3:00).
Ritmo: ~140 palabras por minuto. El texto hablado de esta base suma ~400 palabras: justo. Si un ensayo pasa de 3:00, se recorta primero la parte 3 de la demo.

**Estructura (charla de demo de Platanus):** problema 20–30 s → solución, impacto y ambición 20–30 s → demo 2:00 → gracias.
**El relato:** Andrés corre desde los 13 → la élite sale de cada carrera con datos medidos y comparables; un atleta como él, no → TRAZADA mide con video, igual en cualquier pista, sin equipos caros → se ve en la demo → gracias.
**Reglas que se mantienen:** cifras reales con fuente en pantalla; nada del peor caso "3,8 m por curva"; separar lo que ya funciona de lo que viene.

---

## 1 · Problema · 0:00–0:30 (30 s, ~65 palabras)

> "Hola, soy Andrés y corro desde los 13 años, [800 y 1500]. [En el Nacional de 20XX quedé a X décimas del podio.] ¿Dónde se me fueron? Nadie me lo pudo decir.
> En un Mundial, cada corredor lleva un chip y lo siguen doce cámaras. Y esos metros deciden carreras: en la final de 800 de Río, el plata corrió casi cuatro metros más que el oro. Yo salgo de la pista con un cronómetro y un video en el celular."

**En pantalla:** lámina 2, la foto de Andrés y su frase → lámina 3, **805,3 m** (plata) contra 801,4 m (oro), Río 2016.
**Fuentes:** Omega RTTS (chip en el dorsal) y Seiko VTT (12 cámaras, Mundial Tokio 2025), en `research/trazada/existente.md`. Río: González-Mohíno et al. (2021), *Kinesiology* 53(2):280-287.

**Variantes del arranque para elegir** (todas tienen que ser ciertas):
- **A, la carrera perdida** (la de arriba): un momento concreto con un número. La más fuerte si existe.
- **B, el entrenador:** "Mi entrenador me corregía las curvas a ojo, desde la tribuna. Nunca supimos cuánto me costaban."
- **C, la comparación:** "Cuando vi un análisis de una final de la NCAA, con cada corredor medido, pensé: eso no existe para nosotros."

**Por qué funciona:** el jurado premia que el equipo viva el problema. Pero la historia necesita un momento y un número; "me apasiona el atletismo" sin una escena suena genérico.

## 2 · Solución, impacto y ambición · 0:30–0:55 (25 s, ~60 palabras)

> "Por eso hicimos TRAZADA. Con video, sin chips ni docenas de cámaras, mide a cada corredor en metros: por dónde corrió, cuánto le costó cada curva y dónde le convenía adelantar. Y como todas las pistas siguen el mismo reglamento, se mide igual en Chile que en un Mundial: datos comparables. Partimos por el atletismo, pero sirve para cualquier deporte que se juega en una cancha oficial. Se lo mostramos."

**En pantalla:** lámina 4 (0:30), "La cancha es la regla." con Medido · Comparable · Accesible → lámina 5 (0:45), "Se lo mostramos."; ahí Nico cambia a la app. *[La demo parte 10 s antes: recortar la parte 2 del guion a ~15 s.]*

**Sobre lo que pediste ("estandarizar, unificar, económico"):**
- *Estandarizar y unificar* = "se mide igual en cualquier pista, porque la geometría es oficial". Eso es cierto por diseño (radio 36,5 m, carril 1,22 m de World Athletics) y es nuestro mejor argumento.
- *Económico/accesible* = "sin chips ni docenas de cámaras". **No dar precios** ni decir "con un celular" como si ya funcionara: la demo usa video de TV y la cámara de celular en vivo está solo prototipada.

## 3 · Demo · 0:55–2:45 (1:50) · una sola pantalla

**Hay una sola pantalla:** o se ven las láminas o se ve la app. Al decir "Se lo mostramos", Nico cambia a la app (`Cmd+Tab`) y no vuelve a las láminas hasta el "Gracias". Todo lo de "cómo funciona" se dice **sobre la app**, no con láminas.
**La idea de Andrés:** subir el video en vivo, dejar que cargue y contar lo que pasa. Funciona porque la pantalla de carga ya muestra cada etapa con su nombre. Abajo va una frase concreta por etapa, para que no improvise.

⚠ **Lo primero que hay que medir:** cuánto tarda en cargar el video completo. Si pasa de ~40 s, se come la demo. Opciones: subir un recorte (la última vuelta, ~60 s de video) o tener una pestaña con la carrera ya cargada y saltar a ella si la carga se alarga.

| Tramo | En pantalla (texto real de la app) | Nico hace | Andrés dice |
|---|---|---|---|
| **Subir** · 0:55–1:00 | Panel para arrastrar el video | Arrastra el MP4 | "Esta es la final de 1500 de la NCAA 2025, un video de TV. Lo subo." |
| **Carga 1** · 1:00–1:20 | "Sacando cuadros y buscando corredores…" y la cuadrícula de cuadros | — | "Ahora saca los cuadros del video y en cada uno busca a los corredores. Cada cuadrito es un cuadro: los oscuros ya están revisados, los naranjos son los últimos. El video no se sube entero: solo viajan los cuadros." |
| **Carga 2** · 1:20–1:30 | "Siguiendo a cada corredor…" y el video en bucle con los ya detectados | — | "Ahora une los cuadros: le da a cada corredor una identidad y la mantiene aunque otro lo tape." |
| **Carga 3** · 1:30–1:40 | "Midiendo posición y velocidad…" | — | "Y pasa de píxeles a metros con las medidas oficiales de la pista: 36,5 m de radio, carriles de 1,22 m. Todas las pistas del mundo miden eso; por eso un dato de Chile se compara con uno de un Mundial." |
| **Resultado** · 1:40–2:05 | Cámara con la capa del detector y la etiqueta de la zona; mapa "Dónde está cada atleta" | Play | "Arriba a la derecha, el tramo que está mirando la cámara. Lo difícil es que en una pista todas las líneas se repiten: no hay un área ni un círculo central. El sistema lo deduce con el reglamento y los cortes de cámara. Abajo, cada corredor en la pista, en metros." |
| **Protagonista** · 2:05–2:15 *(recortar a 10 s)* | Lista de corredores → elegir uno (queda en naranja); panel "Cómo cambia la opción de ganar" | Elige al protagonista | "Elijo a [nombre]. [Ganó N puestos en la última vuelta.] Esto es lo que me hubiera servido a mí: cómo cambia su opción de ganar y cuándo le convenía adelantar." *[Ajustar a lo que muestre la captura nueva.]* |
| **Lo que hay debajo** · 2:15–2:30 | Lámina 6 (Nico vuelve a las láminas) | Cambia a las láminas | "Lo que vieron no es un mockup. Cinco etapas: un detector de personas, un seguimiento que mantiene la identidad, un filtro de partículas que deduce qué tramo ve la cámara, un Kalman por atleta y Monte Carlo para pronosticar. Todo anclado a la geometría oficial de la pista." |
| **Impacto y futuro** · 2:30–2:45 | Lámina 7 | → | "Hoy, un atleta y su entrenador ya ven dónde se ganó y dónde se perdió una carrera grabada. Lo siguiente: un celular en la tribuna, en vivo, y datos comparables entre clubes. El sueño: cualquier deporte con cancha oficial, y verlo en AR desde donde estés. La cancha es la regla." → Gracias. |

**Si falla:** si la carga no avanza en 10 s, Nico salta a la pestaña con la carrera ya cargada y Andrés sigue desde "Resultado" sin disculparse. Si no hay internet: tecla V en el deck (grabación).
**Dos pantallas tampoco hacen falta:** el apéndice técnico queda para las preguntas.

## 4 · Gracias · 2:45–2:55 (10 s)

> "Todo lo que pasa en la cancha, en datos para todos. Somos TRAZADA. Gracias."

**En pantalla:** cielo, logo, "Gracias" y la URL. Quedan 5 s de colchón.

---

## Láminas (deck.html)
Ocho láminas principales, porque durante la demo no se ven: **1** Portada (de espera) · **2** Andrés: "Corro desde los 13 años." y su foto · **3** Río: 805,3 m · **4** Solución: La cancha es la regla (0:30) · **5** Demo: "Se lo mostramos." (0:45, Nico cambia a la app) · **6** Lo que hay debajo: del píxel al metro (2:15, Nico vuelve a las láminas) · **7** Impacto y futuro (2:30) · **8** Gracias (2:45).
"Tres desafíos" y "Hoy, lo siguiente y el sueño" pasaron al apéndice (tecla A), por si el jurado pregunta. Salieron "Problema", "Hoy", "Promesa", "Demo" y "Cifra protagonista": su contenido lo dice Andrés o lo muestra la app.

## Frases que NO se dicen
- "3,8 metros por curva" o "10 metros en un 800": es el peor caso geométrico, no algo medido.
- "El plata habría ganado": decir "corrió casi 4 m más".
- "Con un celular" como si ya funcionara: está prototipado.
- Precios o "gratis": no los tenemos.
- "Somos los primeros" o "sin sensores" como novedad: en fútbol ya existe (SkillCorner, Hudl, Veo).
- "Ningún producto lo hace": decir "no encontramos uno para clubes de atletismo".
- "NCCA": es **NCAA**.
- "Precisión de centímetros": los 2–9 cm son de video sintético.
- "86,5 %" sin matiz si preguntan: es contra etiquetas borrador hechas por el equipo.

## Pendientes
- [ ] Andrés: elegir la variante del arranque y completar los corchetes con datos reales (pruebas, la carrera, el año, las décimas).
- [x] Foto de Andrés corriendo (`andres.jpg`, lámina 2).
- [ ] Medir cuánto tarda en cargar el video de la demo y decidir si se usa un recorte.
- [ ] Pestaña de respaldo con la carrera ya cargada.
- [ ] **Captura nueva del front** (la de `demo-captura.png` está desactualizada) y, con ella, los tiempos de la demo.
- [ ] Cifra del protagonista en la demo: puestos y metros.
- [ ] Confirmar con Daniel qué corre en producción: pronóstico y asesor, ¿se muestran o solo se mencionan?
- [x] URL de producción: https://platanus-hack-26-nid.vercel.app (en el pie del Gracias).
- [ ] Ensayar al menos 5 veces con cronómetro (la charla recomendó 3, 5 y 7 o más).

## Fuentes
- González-Mohíno, Casado, Renfree, González-Ravé y Hanley (2021). *Kinesiology* 53(2):280-287. https://hrcak.srce.hr/file/386727
- Omega RTTS y Seiko VTT: `research/trazada/existente.md`.
- Geometría oficial: World Athletics, *Track and Field Facilities Manual*.
- Prototipo de Daniel: `apendice/informe_trazada.pdf`.
