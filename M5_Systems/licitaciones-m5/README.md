# Licitaciones Mercado Público · M5 Industrial

Revisa cada día las licitaciones de Mercado Público (ChileCompra), filtra las que calzan con el
perfil de M5 Industrial (Grupo SHG), las puntúa con Claude, las guarda en Supabase (`m5.licitaciones_mp`)
y deja un reporte en `salida/`. Reemplazó al job `M5_Systems/mercado-publico/` el 19/10/2026.

Etapas: 1 descarga y filtro barato · 2 puntuación con Claude · 3 reporte diario · 4 Supabase ·
5 GitHub Actions (todas hechas).

## Instalación

```
cd M5_Systems/licitaciones-m5
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt        # Windows
```

Dependencias: `requests`, `PyYAML` y el SDK oficial `anthropic` (que trae `pydantic`, usado para validar
el JSON de Claude).

Credenciales **solo por variables de entorno**: `MP_TICKET`, `ANTHROPIC_API_KEY`, `SUPABASE_URL`,
`SUPABASE_KEY`. Para probar en local, copiar `.env.example` a `.env` en esta carpeta y completarlo
(`.env` está en `.gitignore`). En GitHub Actions son secrets del repo `GrupoSHG/Scripts`.

## Configuración

- `config/perfil_m5.yaml`: qué le interesa a M5 (palabras clave, tipos de obra, regiones, montos...).
  Sin `palabras_clave_incluir` o `tipos_de_obra_que_interesan` el proceso no corre. **El repo es
  público**: en el repo queda la plantilla vacía, y el perfil real se completa solo en local o se
  pasa en Actions con el secret `PERFIL_M5_YAML` (el contenido YAML completo), que tiene prioridad
  sobre el archivo. `--perfil RUTA` usa otro archivo.
- `config/ajustes.yaml`: timeouts, reintentos, pausa entre llamadas, tope de solicitudes (80 % de
  10.000 diarias), ventana nocturna 22:00–07:00 y códigos de estado verificados.

## Ejecución local (desde esta carpeta)

```
.venv\Scripts\python -m licitaciones descargar --max 20          # prueba acotada (de día, máx. 50)
.venv\Scripts\python -m licitaciones descargar --fecha 15102026
.venv\Scripts\python -m licitaciones evaluar --max 20             # etapa 2 sobre salida/<hoy>/filtradas.json
.venv\Scripts\python -m licitaciones evaluar --dia 2026-10-19
.venv\Scripts\python -m licitaciones guardar                    # etapa 4: upsert del día en m5.licitaciones_mp
.venv\Scripts\python -m licitaciones reporte                    # etapa 3: salida/<hoy>/reporte.html y reporte.txt
.venv\Scripts\python -m licitaciones detalle 4174-34-LP26        # qué entrega la API para una licitación
.venv\Scripts\python -m unittest discover -s tests -t .
```

Salida en `salida/AAAA-MM-DD/`: `listado.json`, `descartadas.json` (con el motivo), `filtradas.json`
(entrada de la etapa 2) y `embudo.json`; la etapa 2 agrega `evaluadas.json`, `descartadas_claude.json`,
`costo.json` (tokens,
US$ de la corrida y del día) y `evaluacion.md` (tabla para calibrar el perfil).

Códigos de salida: 0 ok · 1 configuración · 2 error de la API de Mercado Público · 3 tope de
solicitudes · 4 error de la API de Claude · 5 tope diario de gasto · 6 más de
`max_revision_manual_por_json` respuestas inválidas · 7 error de Supabase.

Supabase (etapa 4): `supabase/licitaciones_mp_evaluacion.sql` agrega a `m5.licitaciones_mp` las columnas de
la evaluación y crea el rol `licitaciones_m5` (solo leer, insertar y actualizar esa tabla). `SUPABASE_KEY` es
un JWT de ese rol: se genera una vez con `generar_clave_supabase.py` (en tu PowerShell, pide el JWT Secret del
proyecto sin mostrarlo y lo escribe en `.env` y, con `--github`, en los secrets del repo). `guardar` sube las
evaluadas y también las descartadas (para no reevaluarlas; la página no las muestra) y actualiza el estado de
las ya guardadas según el listado del día.

Reporte (etapa 3): `reporte.html` (página autónoma, se abre con doble clic; tema claro y oscuro) y
`reporte.txt` en la carpeta del día, con las mejores del día, las que cierran en `reporte.dias_cierre`
días (de toda la tabla si hay `SUPABASE_URL`/`SUPABASE_KEY`; si no, solo lo del día; las capturadas antes
de la evaluación van en una lista compacta) y las de revisión manual, con enlace a cada ficha. No se
envía por correo ni WhatsApp.

Las evaluaciones las muestra
https://gruposhg-m5-proyectos.netlify.app/licitaciones.html (`GrupoSHG_Systems/M5_Systems/proyectos`).

Evaluación (etapa 2): modelo, esfuerzo, `max_tokens`, precios y tope diario de gasto en
`ajustes.yaml` → `evaluacion` (por defecto `claude-haiku-5-5`, US$ 1 al día). La respuesta tiene esquema
fijo (puntaje 1–5, motivo, tipo de obra, monto, cierre, requisitos, riesgos, recomendación
postular/revisar/descartar) y se valida en local; el monto y la fecha deben ser los publicados o
`null`. Si falla, se reintenta una vez y si no queda "revisar_manualmente". Siguen al reporte y a
Supabase solo las "postular" y "revisar" (más las de revisión manual), en `evaluadas.json`; las
"descartar" quedan en `descartadas_claude.json` (`evaluacion.conservar` en `ajustes.yaml`). La API de Mercado
Público no entrega las bases, así que requisitos y garantías salen solo de la descripción.

Cómo filtra: el listado solo trae código, nombre, estado y cierre, así que primero filtra por
nombre y pide el detalle (1 solicitud) solo de esas; con el detalle vuelve a filtrar por
descripción, ítems, rubro UNSPSC 72, región y monto.

## Precios de referencia de materiales (órdenes de compra de Mercado Público)

Cada noche, después de las licitaciones, el comando `diario` toma las órdenes de compra de ayer cuyo
nombre parece de materiales de construcción (hasta `precios_oc.max_ocs_noche`, 300 por defecto),
guarda solo los datos del producto (sin contactos ni proveedor) y Claude normaliza cada ítem: material
genérico, especificación, presentación y contenido tal como está escrito. Claude no ve precios; el
código convierte unidades y calcula el precio por presentación y por unidad base. Todo queda en
`m5.precios_oc_items` y la vista `m5.precios_referencia` da la mediana de los últimos 90 días por
material, especificación y presentación (SQL en `supabase/precios_oc.sql`). Prueba manual:
`precios-oc --fecha ddmmaaaa --max 50`, `precios-normalizar --dia AAAAMMDD`, `precios-guardar --dia AAAAMMDD`.
Son precios de compradores públicos: sirven de referencia, no reemplazan una cotización.

## Bases, materiales y costo estimado

M5 sube los PDF de bases de una licitación en `licitaciones.html` (bucket privado `licitaciones-bases`, tabla
`m5.licitaciones_bases`) y pide procesarlos (workflow `licitaciones-bases.yml`, `python -m licitaciones bases`;
el comando `diario` procesa los que queden pendientes). Claude lee cada PDF y extrae los materiales con
cantidad y unidad tal como están escritas, usando los mismos nombres que los precios de referencia; el
código convierte a unidad base. La vista `m5.licitaciones_materiales_costo` multiplica cada cantidad por la
mediana de 90 días del material en esa unidad (`m5.precios_material_base`) y `m5.licitaciones_costo_estimado`
resume por licitación con la cobertura (cuántos materiales tienen precio). SQL: `supabase/bases_costos.sql`.
Un PDF cuyo peor caso supera `bases.tope_por_documento_usd` queda en error sin gastar.

## Fichas de postulación

`python -m licitaciones fichas` (y un paso del comando `diario`, después de guardar y antes del reporte; módulo
`fichas.py`, esquema en `ficha_esquema.py`, ajustes en `fichas:` de `ajustes.yaml`). Para cada licitación
publicada con puntaje >= `fichas.puntaje_minimo` (y no "descartar") arma una ficha con datos clave, fechas de
la API, admisibilidad, garantías, criterios, contrato, riesgos, checklist con fecha límite y una recomendación
con 3 razones.

- Los PDF son los del bucket `licitaciones-bases` (la API no entrega las bases). Sin PDF la ficha queda
  "adjuntos pendientes" con el enlace a la ficha oficial; cuando M5 sube PDF nuevos, se rehace.
- Se envía el texto que extrae `pypdf`, con marcas `[DOCUMENTO N]` / `[PÁGINA N]`, en partes de a lo más
  `max_caracteres_por_parte`. Un PDF sin texto queda "escaneado" (sin OCR).
- Claude devuelve una lista plana `{campo, texto, detalle, documento, pagina, cita}`. La salida estructurada
  rechazó un esquema anidado con nulos (más de 16 uniones y luego "grammar too large"). Cada cita se busca en
  el texto de su página y, si no está, se reintenta una vez; lo que sigue sin calzar sale de la ficha y queda
  en "Revisar a mano" (estado `revision_manual`). Lo mismo si el esquema falla dos veces.
- El código calcula días corridos y hábiles (con `fichas.feriados`), porcentajes, montos referenciales de
  garantías y la suma de ponderaciones. Alerta si el cierre está a menos de `dias_habiles_alerta` días hábiles.
- Topes: `tope_por_corrida_usd`, además del diario de la evaluación. Al llegar, la corrida se detiene sin
  fallar y lo que falta queda para la siguiente. Un error en una licitación no detiene a las demás.
- Salida: `m5.licitaciones_fichas` (SQL `supabase/licitaciones_fichas.sql`), `salida/fichas/<código>/ficha.md` y
  `ficha.json`, costo por licitación en `salida/fichas/costos.jsonl`, y la sección "Licitaciones con ficha
  nueva" del reporte (`salida/AAAA-MM-DD/fichas_nuevas.json`). Nada de esto va al artefacto, porque el repo es público.
- Prueba sin guardar nada: `python -m licitaciones fichas --dry-run [--codigo X [--pdf bases.pdf ...]]`.
  Prueba real del 27/10/2026 (3836-36-LP26, 76 páginas): 3 llamadas, US$ 0,022, con 13 documentos
  obligatorios, garantía de fiel cumplimiento y 16 riesgos con página y cita.

## Despliegue

Workflow `.github/workflows/licitaciones.yml` (`python -m licitaciones diario`: las cuatro etapas, omitiendo
las ya evaluadas en Supabase). Sin `schedule:`: lo dispara Supabase a las 22:30 todos los días
(`automatizacion.programa()`, cambio en `supabase/programa_licitaciones.sql`); manual con
`gh workflow run licitaciones.yml -R GrupoSHG/Scripts` (inputs `fecha`, `max`). Secrets del repo:
`MP_TICKET`, `ANTHROPIC_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY` y `PERFIL_M5_YAML` (el perfil en YAML).
El repo es público: el log solo trae cifras agregadas y el artefacto (14 días) solo `embudo.json`,
`costo.json` y `estados_vistos.json`; las evaluaciones se ven con sesión en el dashboard de M5 Proyectos.
Cualquier error termina con código distinto de 0 y la corrida queda en rojo.

Lo verificado contra la API real está en `NOTAS_API.md`.
