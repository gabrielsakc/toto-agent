# Toto agent

Landing + distribución para **Toto agent** — un bulldog cachorro de escritorio
que duerme tranquilo y se despierta a ladrar y correr cuando llega un mail.

Demo en vivo: https://toto-agent.vercel.app
Descarga (Windows): https://github.com/gabrielsakc/toto-agent/releases/latest

## Stack

- Sitio: HTML + CSS estático, desplegado en Vercel
- App: Python 3.10, PyQt6, OpenCV, NumPy, SciPy, imapclient
- Animación: frames extraídos de clips de Veo 3 (Flow) + fondos removidos
  por componentes conectados

## Estructura

```
.
├── index.html        — landing
├── style.css         — estilos
├── hero.png          — imagen del hero
├── preview.mp4       — video del galope (del hero)
├── icon.ico          — favicon
└── vercel.json       — headers para la descarga
```

El `.exe` se distribuye como **GitHub Release**, no vive en este repo.
El código fuente de la app vive en otro repo (a subir por separado).
