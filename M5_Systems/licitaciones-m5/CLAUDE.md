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
- `python -m licitaciones adjudicadas [--dias N] [--max N] [--forzar]` (`adjudicadas.py`)
- `python -m licitaciones fichas [--codigo X] [--max N] [--dry-run [--pdf A.pdf ...]]` (`fichas.py`)
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

## Bases y costo estimado (`bases.py`)

- Comando `bases` (workflow `licitaciones-bases.yml`, botón de licitaciones.html vía `public.actualizar_datos`) y
  respaldo en `diario`. PDF del bucket privado `licitaciones-bases` (el rol `licitaciones_m5` solo lo lee);
  `count_tokens` antes de enviar, tope por documento y tope diario; streaming con `output_config.format`.
- Materiales: reemplaza los de cada PDF (DELETE + INSERT; el rol no tiene UPDATE en esa tabla). El costo lo
  calcula la vista, no Claude. Un material solo tiene precio si coincide la unidad base (m2 de tabique no
  se cruza con el precio por plancha).
- `Presupuesto` aplica `contexto_largo` (Haiku 5.5 x5 sobre 100K tokens de entrada).

## Fichas de postulación (`fichas.py`, `ficha_esquema.py`)

- Paso dentro de `diario` (después de `guardar`, antes del reporte; si falla, se registra y el reporte sigue) y
  comando `fichas [--codigo X] [--max N] [--dry-run [--pdf A.pdf]]`. Candidatas: publicadas con puntaje >=
  `fichas.puntaje_minimo`, no `descartar`, sin cerrar; se rehace la ficha cuando cambian los `bases_ids`.
- PDF solo del bucket `licitaciones-bases` (la API no da adjuntos), leídos con `pypdf` (nunca se abre otro
  formato); se envía el TEXTO por partes, no el PDF. Escaneado = sin OCR, se marca.
- Esquema hacia la API: lista PLANA `datos[{campo, texto, detalle, documento, pagina, cita}]`. No volver a un
  esquema anidado con `anyOf`/null: la API respondió 400 (más de 16 uniones, y luego "compiled grammar is too
  large"). `desde_api` rearma la forma anidada que valida `ExtraccionBases`. Cada cita se verifica contra el
  texto de su página (`verificar_citas`); lo que no calza se quita y deja la ficha en `revision_manual`.
- Claude no calcula nada: días hábiles, montos y porcentajes salen de `calcular` (regex sobre el texto copiado).
- `esfuerzo: medium` y partes de unos 120K caracteres: con `low` y 280K se omitieron los anexos obligatorios.
- Se guarda en `m5.licitaciones_fichas` (SQL `supabase/licitaciones_fichas.sql`, a mano) y en `salida/fichas/`.
  El log y el artefacto llevan solo cifras.

## Obras adjudicadas (`adjudicadas.py`)

- Último paso de `diario` (si falla, se registra y la corrida sigue) y comando `adjudicadas [--dias N] [--max N]
  [--forzar]`. Un listado por día (`fecha=ddmmaaaa&estado=adjudicada`, hoy y los 13 anteriores), filtro por
  nombre (`INCLUIR`/`EXCLUIR`), se omiten las ya guardadas y se pide el detalle de a lo más
  `adjudicadas.max_detalles_noche` (50 fuera de 22:00–07:00), de la más reciente a la más antigua.
- `es_obra` = algún ítem con UNSPSC 72, 30 o 95; las que no, se guardan igual para no volver a pedirlas y
  la pestaña no las muestra. Ganadores desde `Items.Listado[].Adjudicacion` (monto = cantidad x unitario).
- RUT y razón social del adjudicado solo si es empresa (RUT desde 50.000.000); si no, "Persona natural".
- Tabla `m5.licitaciones_adjudicadas` (SQL `supabase/licitaciones_adjudicadas.sql`, a mano); la lee
  `GrupoSHG_Systems/cockpit-comercial-web/tabs/tab-adjudicadas.js` (últimos 14 días).

## API (ver NOTAS_API.md)

10.000 solicitudes/día por ticket; el proceso para al 80 %. Descargas masivas solo 22:00–07:00 de
Chile: fuera de esa ventana se niega a pedir más de 50 detalles sin `--forzar`. Ticket inválido =
HTTP 203; 403 corta sin reintentar; 429/5xx con reintentos acotados (429 persistente corta la
corrida). Los códigos de estado reales difieren de la documentación (Revocada = 15, no 18).
