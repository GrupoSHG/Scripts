# Licitaciones Mercado Público · M5 Industrial

Consulta la API de Mercado Público (ChileCompra) y detecta licitaciones de obras relevantes para M5.
Documentación de la API: https://www.chilecompra.cl/api/

## Instalar

```
cd M5_Systems/mercado-publico
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Configurar

- **Credenciales** solo por variables de entorno: `MP_TICKET` (ticket de la API) y, desde la etapa 3,
  `SUPABASE_SERVICE_KEY`. Para probar en local, copiar `.env.example` a `.env` (en esta carpeta o en la
  raíz del repo `Scripts`) y completarlo; `.env` está en `.gitignore`. Nunca poner el ticket en el código.
- **`config.json`**: timeouts, reintentos, pausa entre llamadas, límite diario (10.000) y tope (80 %),
  ventana de cargas masivas (22:00–07:00, hora de Chile).
- El contador de solicitudes del día queda en `estado/solicitudes_AAAAMMDD.json` (no se sube a git).
  Al llegar al tope el proceso se detiene.

## Ejecutar

```
.venv\Scripts\python prueba.py        # licitaciones activas: cantidad y las 10 primeras
```
