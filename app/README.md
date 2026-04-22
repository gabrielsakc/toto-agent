# Bulldog desktop pet

Un cachorro bulldog inglés fotorrealista que duerme en la esquina inferior
derecha de tu pantalla y se despierta a ladrar + correr cuando llega un mail.

## Primer arranque

```bat
cd "D:\Web Pte Power\desktop-pet"
C:\Python310\python.exe main.py
```

Verás al perro dormitando (respirando) abajo a la derecha. En la bandeja
del sistema aparece un icono con el menú:

- **Test: bark + run** — dispara la animación completa sin necesidad de mail
- **Quit** — cierra la app

## Conectar Gmail

1. Activa verificación en dos pasos en tu cuenta de Google:
   https://myaccount.google.com/security
2. Crea una *App password* ("Contraseñas de aplicaciones"):
   https://myaccount.google.com/apppasswords
   → elige "Mail" / "Windows Computer" → copia los 16 caracteres.
3. Copia el ejemplo y edítalo:

```bat
copy config.example.json config.json
notepad config.json
```

Rellena:

```json
{
  "pet_height_px": 180,
  "gmail": {
    "enabled": true,
    "username": "gabrielsakc@gmail.com",
    "app_password": "abcdefghijklmnop"
  }
}
```

4. Vuelve a ejecutar `main.py`. Cada mail nuevo en INBOX dispara la animación.

## Cambiar tamaño / posición

- `pet_height_px` en `config.json` — altura en píxeles (default 180)
- `margin_px` — separación de los bordes del escritorio
- El anchor está en la esquina inferior derecha; para otra posición hay que
  tocar `pet.py` (`anchor_right` / `baseline_y`).

## Arranque automático con Windows

Crea un acceso directo a:

```
C:\Python310\pythonw.exe "D:\Web Pte Power\desktop-pet\main.py"
```

Nota: `pythonw.exe` en vez de `python.exe` evita la ventana de consola.

Pégalo en:

```
%AppData%\Microsoft\Windows\Start Menu\Programs\Startup
```

## Archivos

```
desktop-pet/
├── main.py                  entry point
├── pet.py                   widget + state machine
├── mail_monitor.py          Gmail IMAP hilo
├── prep_assets.py           (ya ejecutado) preprocesa imágenes
├── config.example.json      plantilla
├── requirements.txt
├── assets/                  originales (JPEG/PNG con fondo blanco)
└── assets_processed/        PNGs con fondo transparente (los que usa la app)
```

Si generas nuevas fotos, cópialas a `assets/` con los nombres esperados
(`bark.jpeg`, `run_01.jpeg`, etc.) y corre `python prep_assets.py`.
