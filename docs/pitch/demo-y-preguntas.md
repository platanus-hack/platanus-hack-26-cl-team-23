# TRAZADA · Plan de demo y preguntas del jurado · v2

Roles: **Andrés** presenta y narra la demo · **Nico** maneja el teclado (diapositivas y demo) · **Daniel** responde lo técnico en las preguntas.
Video de la demo: **final de 1500 m varones NCAA 2025** (no "NCCA").

## Plan de demo

**Plan A · producto en producción**
- Laptop de Nico, Chrome en pantalla completa, URL de producción ya cargada y el video reproducido una vez antes de subir (que quede en caché).
- Corredor protagonista elegido de antemano; video pausado en el cuadro 0.
- Diapositivas en otra pestaña; Nico cambia con `Cmd+Tab` cuando Andrés dice "Se lo mostramos". Ensayar el cambio.
- No depender del WiFi del evento: probar que la página cargue con el hotspot de un celular.

**Plan B · grabación de pantalla (MP4, 60 s)**
- Grabarla en el punto de control de las 03:00, con la demo completa y sin audio.
- Va oculta en el deck (tecla V). Si el sitio no carga en 10 s, Nico la abre y Andrés narra igual: "Les muestro la grabación de hace unas horas". Sin disculpas largas.
- Copia en la laptop y en un pendrive.

**Plan C · si el trabajo de Daniel no está integrado en producción**
- El modo "Simulación" ya no existe en `dev`, así que no se puede usar como respaldo.
- Si producción muestra corredores pero no metros: 10 s de video real en el producto ("esto ve el sistema") y luego la salida del prototipo de Daniel (video con la zona y los atletas encima, `render_zones.py`), diciendo que es el prototipo. Grabarla antes en MP4, junto con el plan B.

**Checklist 30 min antes**
- [ ] URL de producción abre desde otro celular (4G)
- [ ] Cifras del protagonista anotadas en el guion
- [ ] MP4 de respaldo abre sin internet
- [ ] Brillo al máximo, notificaciones apagadas, No molestar
- [ ] Cargador y adaptador HDMI/USB-C
- [ ] Alguien del equipo levanta la mano a las 2:30

## Preguntas probables del jurado

Quién responde entre paréntesis. Las respuestas son guías, no textos para memorizar.

**Técnico (25)**
1. **¿Cómo saben qué parte de la pista ve la cámara si todas las curvas se parecen?** *(Daniel)* — Un filtro causal que combina el reglamento (dónde parte la prueba y el reloj de carrera), la forma de las líneas (recta o curva), los cortes de cámara y una memoria de las cámaras que aprende sobre la marcha. En la final NCAA 2025 acierta el 86,5 % contra etiquetas que hicimos nosotros, en borrador; con solo el reglamento sería el 50 %.
2. **¿Cómo pasan de píxeles a metros?** *(Daniel)* — Con las medidas oficiales de World Athletics (radio 36,5 m, pista 1,22 m) calculamos una homografía: una transformación que lleva cada punto de la imagen al plano de la pista. De ahí salen dos números por corredor: cuánto avanzó (s) y a qué distancia de la cuerda va (d). Los metros extra salen de d en las curvas.
3. **¿Qué pasa cuando un corredor tapa a otro?** *(Andrés)* — Es el riesgo principal; incluso el paper japonés de 2023 lo tuvo con un solo corredor. ByteTrack mantiene la identidad 2 s sin detección, y si se pierde la re-unimos prediciendo dónde debería estar en metros. Si el salto es físicamente imposible, soltamos el ID en vez de inventar.
4. **¿Qué tan preciso es?** *(Daniel)* — En video sintético, con verdad conocida, el error es de 2 a 9 cm. En video real todavía no lo validamos contra una medición independiente; lo siguiente es compararlo con parciales cada 100 m, como hacen los estudios. *[Actualizar si miden algo con NCAA.]*
5. **¿Por qué dicen "en vivo" si muestran un video grabado?** *(Daniel)* — Todo el cálculo es causal: cada cuadro usa solo el pasado, como llegaría de una cámara. La entrada con cámara en vivo y la salida por WebSocket ya están prototipadas.
6. **¿Entrenaron un modelo?** *(Andrés)* — No para la pista. Usamos detectores de personas preentrenados y la geometría oficial. Roboflow hace esto en fútbol con 32 puntos únicos de la cancha; la pista no los tiene, por eso existe el paso de las zonas.

**Originalidad (15)**
7. **¿Esto no existe ya?** — Omega, Seiko y Sony siguen corredores en la élite con chips o docenas de cámaras, y muestran velocidad y parciales. Los estudios calculan los metros extra a mano, después. Para clubes encontramos apps de cronómetro. El paper de 2023 dice ser el primer seguimiento automático en medio fondo, con un solo corredor.
7b. **¿Y SkillCorner, Hudl o Veo? Eso ya mide fútbol con video.** — Sí, y eso prueba que el mercado existe. Ninguno trabaja en atletismo de pista, y nadie muestra los metros extra por curva. Lo difícil de la pista es que no tiene puntos únicos como el área o el círculo central: las líneas se repiten. Por eso tuvimos que resolver primero qué tramo mira la cámara.
8. **¿Por qué no un GPS o un reloj?** — Un dispositivo por atleta, caro, y el GPS no está validado en curvas de pista. Con video, una cámara mide a todos, también a los rivales.

**Impacto (20)**
9. **¿Quién lo usaría primero?** — El entrenador de club de medio fondo y el atleta máster, que paga de su bolsillo. En Chile no encontramos análisis táctico por video ni en el alto rendimiento. Y como todas las pistas de 400 m son iguales, sirve en cualquier país. *(No inventar precios.)*
10. **¿De verdad importan cuatro décimas?** — En el 800 de Río, el plata corrió casi 4 m más que el oro, y a nivel no élite la pérdida medida fue mayor (+10 m en un 1500). Además, el valor no es solo el número: es saber dónde convino adelantar.
11. **¿Hablaron con entrenadores?** — *[Completar con las respuestas de la red de Andrés; si no hay, decirlo: validar es el siguiente paso.]*

**Ambición (20)**
12. **¿Por qué creen que sirve para otros deportes?** — Todo deporte reglamentado tiene una geometría oficial que sirve de regla. Ya se usa en fútbol (Roboflow) y hay investigación en remo. Nosotros resolvimos el caso difícil: una pista sin puntos únicos.
13. **¿Qué falta para la transmisión en vivo?** — Infraestructura y latencia: el algoritmo ya es causal. El video de TV es experimental porque la cámara se mueve y hace zoom.

**Ejecución (20)**
14. **¿Qué funciona hoy y qué es simulado?** — Decirlo con precisión. *[Llenar el domingo a las 08:00: detección y seguimiento ✔/✘ · zona de la pista ✔/✘ · metros por corredor ✔/✘ · en producción ✔/✘.]*
15. **¿Por qué el track Physical World?** — La entrada es una señal física real: video de una cámara apuntando a una pista real, medido en metros reales.

## Apéndice técnico (deck, tecla A)
Lo responde Daniel; fuente: `apendice/informe_trazada.pdf`. Láminas: así se ve por dentro · zona del grupo (86,5 %) · cada atleta sin calibrar (cuerpo 1,75 m, calle 1,22 m) · quién compite · atletas ocultos · pronóstico (1,0 s en los últimos 200 m) · cuándo adelantar · qué falta.

16. **¿Cómo funciona con una cámara de TV que se mueve?** *(Daniel)* — Separamos dónde está el grupo (filtro de partículas con reglamento, cortes, memoria de encuadres, curvatura y velocidad contra el suelo) de cómo se ordenan los atletas dentro del cuadro (alto del cuerpo y ancho de calle, sin calibrar). → láminas de zona y de cada atleta.
17. **¿Cómo distinguen a un corredor de un juez o del público?** *(Daniel)* — Cinco filtros físicos: fuera de los gráficos, pies sobre tartán, tamaño parecido al grupo, nunca más atletas que en la serie, saltos imposibles. Límite honesto: un juez sobre el tartán pasaría.
18. **¿Qué pasa si un corredor queda tapado?** *(Daniel)* — Sigue avanzando con la velocidad del grupo y su incertidumbre crece; se re-identifica al reaparecer (identidad recordada 40 s).
19. **¿Pueden predecir quién gana?** *(Daniel)* — Hay un pronóstico en vivo: 1,0 s de error en el tiempo ganador en los últimos 200 m, 3,5–6,9 s en la primera mitad. Una sola carrera, intervalos todavía angostos.
20. **¿Y lo de cuándo adelantar?** *(Daniel)* — Un asesor con energía (velocidad crítica y reserva), rebufo y costo de curva. Se comporta bien en tests; falta validarlo con adelantamientos reales.
