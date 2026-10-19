# Scripts

Automatizaciones de Grupo SHG: todo lo que corre programado (GitHub Actions
disparado desde Supabase `pg_cron`) y llena las tablas que leen los dashboards
de `GrupoSHG_Systems`.

## Orden del repo

Lo transversal al grupo queda en la raíz; lo de cada empresa va en su carpeta `<Empresa>_Systems`
(mismos nombres que en `GrupoSHG_Systems`).

| Carpeta | Contenido |
|---|---|
| `automatizacion/` | SQL del disparador `pg_cron` y del botón "Actualizar datos" (transversal) |
| `.github/` | Workflows (`workflow_dispatch`, sin `schedule`) y el script de monitoreo (transversal) |
| `Polchile_Systems/` | `manager-robot-horario/` (robot Playwright que descarga de Manager cada hora, workflow `manager-descargas.yml`), `manager-pipeline-diario/` (pipeline diario que restaura el `.bak` de Manager y carga todo a Supabase, workflow `pipeline.yml`), `sync_ghl_polchile.py` + `carga_polchile_crm.sql` (CRM GoHighLevel → `polchile_crm`), `polchile-cockpit/` y `gestion-ordenes-compra/` (sitios Firebase legacy) |
| `M5_Systems/` | `sync_ghl_m5.py` (CRM GoHighLevel → esquema `m5`) |
| `HEA_Systems/` | `hea-hojalateria/` (sitio Firebase legacy) |
| `polchile-systems/` | Copia antigua de `GrupoSHG_Systems`; no editar |

Los workflows en `.github/workflows/` apuntan a estas rutas
(`Polchile_Systems/manager-robot-horario`, `Polchile_Systems/manager-pipeline-diario`,
`Polchile_Systems/sync_ghl_polchile.py`, `M5_Systems/sync_ghl_m5.py`).
