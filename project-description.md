# TRAZADA

**TRAZADA mide lo que el cronómetro no ve.** Sigue a cada corredor en un video de pista y lo ubica sobre una pista de 400 m a escala, para mostrar cuánto corre de más quien va por fuera en la curva.

## El problema

En una carrera de 400 m el cronómetro da un tiempo, pero no cuenta cómo se corrió. Quien va por un carril exterior o se abre en la curva recorre más metros que quien va pegado a la cuerda, y eso casi nunca se ve en una transmisión.

## Qué hace

- **Seguimiento:** detecta a cada atleta en el video y le asigna un id estable durante toda la carrera.
- **Vista cenital:** ubica a cada corredor en una pista de 400 m vista desde arriba, con sus ocho carriles.
- **Zona de cámara:** indica qué tramo de la pista enfoca la cámara en cada cuadro.
- **Relato con voz:** narra la carrera por tramos. El guion no puede inventar: toda cifra se verifica contra los datos medidos antes de sintetizar el audio, y si no pasa se usan plantillas deterministas.

## Cómo funciona

1. El navegador saca cuadros a 10 fps y envía solo esos, no el video completo.
2. El backend detecta y sigue a los corredores (ByteTrack) y estima la zona de pista que ve la cámara.
3. Con eso arma los hechos de la carrera y genera el relato con Claude y la voz con ElevenLabs.
4. La interfaz muestra el video con las cajas, la lista de corredores, la vista cenital y el relato sincronizado con el play.

## Stack

React 19 · Vite · TypeScript · Tailwind CSS 4 · FastAPI · Python 3.13 · ByteTrack · Claude · ElevenLabs · Vercel

## Equipo

Daniel Acuña Ureta, Nicolás Cruzat y Andrés Sebastian — team-23, Platanus Hack 26 Santiago.
