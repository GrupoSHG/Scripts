# Licitaciones Mercado Público · M5 Industrial

Consulta la API de Mercado Público (ChileCompra), detecta licitaciones de obras relevantes para M5
y las guarda en Supabase (`m5.licitaciones_mp`). Las muestra la página
https://gruposhg-m5-proyectos.netlify.app/licitaciones.html (repo `GrupoSHG_Systems`,
`M5_Systems/proyectos/licitaciones.html`). Documentación de la API: https://www.chilecompra.cl/api/
Lo verificado contra la API real (códigos de estado, 429, forma de las respuestas) está en `NOTAS_API.md`.

## Instalar

```
cd M5_Systems/mercado-publico
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Configurar

- **Credenciales** solo por variables de entorno: `MP_TICKET` (ticket de la API) y
  `SUPABASE_SERVICE_KEY` (solo con `--supabase`). Para probar en local, copiar `.env.example` a `.env`
  (en esta carpeta o en la raíz del repo `Scripts`) y completarlo; `.env` está en `.gitignore`.
  En GitHub Actions son secrets del repo.
- **`config.json`** (editable, sin tocar código):
  - `palabras_clave` / `exclusiones`: sin tildes ni mayúsculas, desde el inicio de palabra. Una
    exclusión en el nombre descarta la licitación.
  - `estados` (códigos verificados) y `estados_a_descargar` (5 = Publicada).
  - `api`: timeouts, reintentos, pausa entre llamadas (1,5 s: con menos la API responde 429).
  - `limites`: 10.000 solicitudes diarias, tope 80 %. El contador del día (hora de Chile) queda en
    `estado/solicitudes_AAAAMMDD.json`; al llegar al tope el proceso se detiene y guarda lo hecho.
  - `horario`: ventana de cargas masivas 22:00–07:00. Fuera de ella el proceso se niega a pedir más de
    `max_solicitudes_fuera_de_horario` detalles (salvo `--forzar`).
- **Supabase**: aplicar una vez `licitaciones_mp.sql` (tabla, RLS de solo lectura para usuarios con sesión).

## Ejecutar

```
.venv\Scripts\python prueba.py                       # licitaciones activas: cantidad y las 10 primeras
.venv\Scripts\python descarga_diaria.py              # hoy y ayer -> salida/ (reporte_AAAAMMDD.md)
.venv\Scripts\python descarga_diaria.py --fecha 15102026 --max 20   # prueba acotada
.venv\Scripts\python descarga_diaria.py --supabase   # además upsert en m5.licitaciones_mp
.venv\Scripts\python descarga_diaria.py --activas --supabase        # carga inicial (de noche)
```

Con `--supabase` y la tabla vacía, la primera corrida hace sola la carga inicial desde todas las activas.

Cómo filtra: el listado trae solo código, nombre, estado y cierre, así que primero filtra por nombre y
solo pide el detalle (1 solicitud cada una) de las candidatas; con el detalle vuelve a filtrar por
descripción, ítems y rubro UNSPSC 72. Las ya guardadas no se vuelven a pedir: si aparecen en el listado
con otro estado, se actualiza el estado.

Salida en `salida/`: `reporte_AAAAMMDD.md` (nuevas relevantes + las que cierran en los próximos 7 días),
`licitaciones_AAAAMMDD.json`, `historico.json`, `estados_vistos.json`.

Programado: workflow `.github/workflows/mercado-publico-m5.yml` (`--supabase`; inputs `activas`, `fecha`),
disparado por `automatizacion.programa()` en Supabase dentro de la ventana nocturna.
