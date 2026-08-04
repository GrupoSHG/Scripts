# RCV Polchile — Backend

Guarda todas las credenciales sensibles (certificado digital, passwords,
ApiKeys) en el servidor. El frontend (carpeta `areafinanzas/`) nunca las ve.

## Estructura

```
(carpeta del proyecto)/
├── app.py
├── requirements.txt
├── .env.example
├── .gitignore
├── secrets/
│   └── certificado.pfx   ← tu certificado digital va aquí
└── areafinanzas/
    ├── index.html
    ├── app.js
    └── styles.css
```

## Instalación

```bash
python -m venv venv
venv\Scripts\activate        # Windows (PowerShell: venv\Scripts\Activate.ps1)
pip install -r requirements.txt
```

## Configuración

1. Copia `.env.example` a `.env`
2. Completa tus datos reales en `.env`
3. Coloca tu certificado digital en `secrets/certificado.pfx` (o la ruta que definas en `PFX_PATH`)

`secrets/` y `.env` están en `.gitignore` — **nunca se suben a GitHub.**

## Ejecutar

```bash
python app.py
```

Abre `http://127.0.0.1:5000` — ahí se sirve `areafinanzas/index.html`, ya conectado al backend.

## Endpoints

- `GET /api/rcv?periodo=2026-07` → consulta compras y ventas del SII para ese período (demora 40-120s, es scraping real)
- `POST /api/manager/upload` → recibe `{ tipo: "compra"|"venta", documentos: [...] }` y los carga a Manager
- `GET /api/manager/status` → indica si la conexión a Manager está configurada

## Notas

- El parseo de la respuesta de SimpleAPI (`extraer_documentos` en `app.py`) es defensivo porque la documentación pública no mostraba la forma completa del JSON. Si al probar con datos reales no calzan los campos, revisa la respuesta cruda (agrega un `print(raw_compras)` temporal) y ajusta las llaves.
- El path exacto y los campos de Manager (`purchase-invoice-form` / `sales-invoice-form`) también conviene confirmarlos contra tu instancia real.

## Deploy en Render (backend)

Netlify no sirve para este backend (procesos de 40-120s, certificado .pfx, IMAP) —
usa Render en su lugar.

1. Sube el proyecto a GitHub (ya lo tienes hecho).
2. En [render.com](https://render.com): **New → Web Service** → conecta tu repo.
3. Configuración:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app` (ya incluido en el `Procfile`)
4. En la pestaña **Environment**, agrega TODAS las variables de tu `.env` una por una (Render no lee archivos `.env`, se configuran ahí).
5. Para el certificado `.pfx`: como no puedes copiar un archivo directo al repo,
   conviértelo a base64 y pégalo en la variable `PFX_BASE64`:
   ```powershell
   [Convert]::ToBase64String([IO.File]::ReadAllBytes("certificado.pfx")) | Set-Clipboard
   ```
   Pega el resultado (ya en el portapapeles) como valor de `PFX_BASE64` en Render.
   No necesitas configurar `PFX_PATH` en este caso (usa el default).
6. Deploy. Render te da una URL pública (ej. `https://rcv-polchile.onrender.com`) — ahí queda todo, frontend y backend juntos.

**Nota sobre el plan gratuito de Render**: el servicio "duerme" tras 15 min sin uso y demora ~30-50s en despertar en la primera petición. Si eso molesta para el uso diario, el plan pagado (desde ~US$7/mes) lo mantiene siempre activo.
