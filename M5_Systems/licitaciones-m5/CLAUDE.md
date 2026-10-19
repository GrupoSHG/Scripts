# CLAUDE.md · M5_Systems/licitaciones-m5

Guía para Claude Code en esta carpeta del repo `GrupoSHG/Scripts`. Responder al usuario en español;
código, comentarios y textos también en español.

## Qué es

Proceso diario de M5 Industrial (Grupo SHG): descarga licitaciones de la API de Mercado Público,
las filtra con `config/perfil_m5.yaml` y (etapas siguientes) las puntúa con Claude, genera un
reporte y las guarda en Supabase (`m5.licitaciones_mp`, proyecto `ffxopvzxyeacpbtxuagu`; la lee
`GrupoSHG_Systems/M5_Systems/proyectos/licitaciones.html`). Reemplaza a `../mercado-publico/`
(workflow `mercado-publico-m5.yml`, disparado por `automatizacion.programa()` a las 22:30), que se
retira en la etapa 5: ambos usan el mismo ticket y no deben correr los dos.

**`Scripts` es un repo PÚBLICO**: el código, `config/` y los artefactos de Actions los puede ver
cualquiera. No subir datos comerciales sensibles de M5 ni evaluaciones al repo.

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
- `python -m licitaciones detalle CODIGO`

## API (ver NOTAS_API.md)

10.000 solicitudes/día por ticket; el proceso para al 80 %. Descargas masivas solo 22:00–07:00 de
Chile: fuera de esa ventana se niega a pedir más de 50 detalles sin `--forzar`. Ticket inválido =
HTTP 203; 403 corta sin reintentar; 429/5xx con reintentos acotados (429 persistente corta la
corrida). Los códigos de estado reales difieren de la documentación (Revocada = 15, no 18).
