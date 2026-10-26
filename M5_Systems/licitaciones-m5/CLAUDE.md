# CLAUDE.md · M5_Systems/licitaciones-m5

Guía para Claude Code en esta carpeta del repo `GrupoSHG/Scripts`. Responder al usuario en español;
código, comentarios y textos también en español.

## Qué es

Proceso diario de M5 Industrial (Grupo SHG): descarga licitaciones de la API de Mercado Público,
las filtra con `config/perfil_m5.yaml` y (etapas siguientes) las puntúa con Claude, genera un
reporte y las guarda en Supabase (`m5.licitaciones_mp`, proyecto `ffxopvzxyeacpbtxuagu`; la lee
`GrupoSHG_Systems/M5_Systems/proyectos/licitaciones.html`). Workflow `.github/workflows/licitaciones.yml`
(`python -m licitaciones diario`), disparado por `automatizacion.programa()` a las 22:30; reemplazó el
19/10/2026 al job `M5_Systems/mercado-publico/` (`mercado-publico-m5.yml`, borrado).

**`Scripts` es un repo PÚBLICO**: el código, `config/`, el log y los artefactos de Actions los puede ver
cualquiera. No subir datos comerciales sensibles de M5 ni evaluaciones al repo: el perfil real va en el
secret `PERFIL_M5_YAML`, el detalle de cada evaluación se loguea en DEBUG y el artefacto lleva solo
`embudo.json`, `costo.json` y `estados_vistos.json`.

## Reglas de seguridad

- Credenciales solo desde variables de entorno (`MP_TICKET`, `ANTHROPIC_API_KEY`, `SUPABASE_URL`,
  `SUPABASE_KEY`); `config.cargar_env()` lee únicamente el `.env` de esta carpeta. No pedir, leer,
  imprimir ni buscar sus valores.
- El ticket va como parámetro de la URL: no registrar URLs ni el texto de excepciones de `requests`.
  Todo log pasa por `config.FiltroSecretos` / `enmascarar`.
- Del detalle de la API se guarda solo la lista blanca de `licitaciones/detalle.py` (trae nombres,
  correos y teléfonos de funcionarios).
- Antes de cada commit: `git diff --cached` y un grep de claves/tickets/tokens. `salida/`, `estado/`
  y `.env` están en `.gitignore`.

## Comandos (desde esta carpeta)

- Pruebas: `python -m unittest discover -s tests -t .` (sin red, con sesión falsa).
- `python -m licitaciones descargar [--fecha ddmmaaaa] [--max N] [--forzar]`
- `python -m licitaciones evaluar [--dia AAAA-MM-DD] [--max N] [--perfil RUTA]` (etapa 2, `evaluacion.py`)
- `python -m licitaciones detalle CODIGO`
- `python -m licitaciones guardar [--dia AAAA-MM-DD]` (etapa 4, `supabase_mp.py`, REST con `requests`).
- `python -m licitaciones reporte [--dia AAAA-MM-DD] [--sin-supabase]` (etapa 3, `reporte.py`; todo texto con
  `html.escape`, solo escribe archivos, nunca envía).
- Códigos de salida: 1 config · 2 API MP · 3 tope solicitudes · 4 API Claude · 5 tope gasto · 6 JSON inválido ·
  7 Supabase.
- Supabase: `SUPABASE_KEY` = JWT del rol `licitaciones_m5` (SQL en `supabase/`, generado por el usuario con
  `generar_clave_supabase.py`); `apikey` = clave publicable de `ajustes.yaml` (pública). No usar la
  `SUPABASE_SERVICE_KEY` del repo. La página `licitaciones.html` de `GrupoSHG_Systems` oculta `descartar`.
- Claude: SDK `anthropic` con `api_key` explícita desde `ANTHROPIC_API_KEY` (no usar perfiles `ant`),
  `output_config.format` con `ESQUEMA` + validación local con `Evaluacion` (pydantic). Si se cambia el
  modelo, agregar su precio en `ajustes.yaml` o el tope de gasto no corre.

## Precios de referencia (`precios_oc.py`, `normalizacion.py`)

- Paso `precios_oc.nocturno` dentro de `diario` (`ajustes.yaml` → `precios_oc`): órdenes de compra de
  ayer, filtro por nombre, detalle con lista blanca, normalización con Claude en lotes de 25 y upsert en
  `m5.precios_oc_items` (clave `oc, correlativo`) con el rol `licitaciones_m5`. Fuera de 22:00–07:00 pide
  a lo más 50 detalles.
- Claude nunca recibe ni devuelve precios y copia el contenido tal como está escrito (`300 ml`): la
  conversión a unidad base la hace `CONVERSION` en el código (el modelo convertía mal ml→litro y g→kg).
- `PrecioNeto` de la OC es por unidad y sin IVA; `Unidad` viene siempre vacía (ver NOTAS_API.md).

## API (ver NOTAS_API.md)

10.000 solicitudes/día por ticket; el proceso para al 80 %. Descargas masivas solo 22:00–07:00 de
Chile: fuera de esa ventana se niega a pedir más de 50 detalles sin `--forzar`. Ticket inválido =
HTTP 203; 403 corta sin reintentar; 429/5xx con reintentos acotados (429 persistente corta la
corrida). Los códigos de estado reales difieren de la documentación (Revocada = 15, no 18).
