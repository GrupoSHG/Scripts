# Agentes IA de la Oficina de Agentes

Resuelve las instrucciones que se dan en la Oficina de Agentes
(https://gruposhg-oficina.netlify.app, código en `GrupoSHG_Systems/oficina-agentes/`).

## Cómo fluye una instrucción

1. En la Oficina, un admin o director le escribe a un agente. La página llama a
   `public.agente_instruir(agente, texto, parametros)`, que guarda la fila en
   `shg_dashboards.agentes_instrucciones` (estado `pendiente`) y dispara `agente-ia.yml` con
   **solo el id** (este repo es público).
2. El workflow corre `python -m agentes ejecutar --id N`: marca la fila `trabajando`, resuelve
   la instrucción y deja `respuesta`, `costo_usd` y `tokens` (o `error`) en la misma fila.
3. La Oficina lee la fila con `public.oficina_estado()` cada 15 s y muestra la respuesta.

## Agentes

| Id | Agente | Qué hace |
|---|---|---|
| `comercial` | Analista Comercial | Claude (`claude-opus-5-5`) con la herramienta `consultar_sql` |
| `finanzas` | Analista Finanzas | igual, con foco en CxC, compras, RCV y cheques |
| `planta` | Planificador Planta | igual, con foco en OP, WIP, materiales y despachos |
| `dev` | Desarrollador | Claude Code sin interfaz sobre un clon de `GrupoSHG_Systems` o `Scripts`; abre un **PR en borrador** (rama `agente/<id>-...`), nunca fusiona ni publica |

Los analistas solo leen datos a través de `public.agente_consulta(sql)`, que corre como el rol
`agentes_lectura` (solo `SELECT` sobre `shg_dashboards`, `polchile_crm`, `m5`, `app_cys`,
`stock_productos` y `hea`, sin `auth`, `vault` ni `automatizacion`) dentro de una transacción de
solo lectura.

Cada analista tiene su **mapa de datos** en `perfiles.py` (`FUENTES`): qué tabla usar para cada
cosa, sus columnas clave, cuándo se actualiza y las trampas conocidas (por ejemplo, las NCV de
`ventas_full` vienen en positivo y hay que restarlas). Va al prompt y el agente busca ahí primero;
solo si no está, explora `information_schema` y lo dice. La ficha de la Oficina muestra el mismo
mapa (`GrupoSHG_Systems/oficina-agentes/agentes.js`): si cambia una tabla, cambiar los dos.

## Topes de gasto

- Por día (hora de Santiago), sumando todas las instrucciones: `AGENTES_TOPE_DIARIO_USD`, por defecto US$ 5.
- Por instrucción: `AGENTES_TOPE_INSTRUCCION_USD` (analistas, US$ 1,5) y `AGENTES_TOPE_DEV_USD` (Desarrollador, US$ 3).
- `public.agente_instruir` no acepta más de 6 instrucciones abiertas a la vez.

Se cambian como variables del repo (Settings → Secrets and variables → Actions → Variables).

## Puesta en marcha

1. Aplicar `automatizacion/oficina_agentes.sql` en Supabase.
2. Secrets del repo: `ANTHROPIC_API_KEY` y `SUPABASE_SERVICE_KEY` ya existen. Para el Desarrollador,
   crear `AGENTES_GH_TOKEN`: PAT fine-grained con dueño GrupoSHG, repos `GrupoSHG_Systems` y
   `Scripts`, permisos Contents y Pull requests en lectura y escritura. Sin él, las instrucciones
   al Desarrollador terminan en error con ese aviso; los analistas funcionan igual.

## Correr a mano

```
pip install -r requirements.txt
python -m unittest discover -s tests -t .       # pruebas sin red
python -m agentes ejecutar --id 12              # con ANTHROPIC_API_KEY y SUPABASE_SERVICE_KEY
```

Una instrucción solo se resuelve si está `pendiente`. Para reintentar una que quedó en `error`,
crear otra desde la Oficina.

## Repo público

El log solo muestra el id, el agente, el número de consultas y el costo; el Desarrollador no
imprime la salida de Claude Code ni de git. El título y el cuerpo del PR que abre el
Desarrollador sí llevan la instrucción: en `Scripts` (público) ese PR es visible para todos.
