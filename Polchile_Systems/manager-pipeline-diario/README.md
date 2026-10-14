# Pipeline diario de Manager (`manager-pipeline-diario/`)

Hasta octubre de 2026 esta carpeta se llamaba `backup-manager/`. Se renombró para que el
nombre diga lo que hace y se distinga del robot horario (`manager-robot-horario/`):

| Carpeta | Qué hace | Cuándo | Workflow |
|---|---|---|---|
| `manager-robot-horario/` | Entra a Manager con un navegador y descarga 5 informes (pendientes FAV, ventas full, notas de venta, OP, stock) a `shg_dashboards` | lun–vie, cada hora 09:07–18:07 | `manager-descargas.yml` |
| `manager-pipeline-diario/` (esta) | Descarga el respaldo `.bak` de Manager, lo restaura en un SQL Server del runner, extrae las consultas de `ConsultasSQL/` y las carga a Supabase; sube el Excel de Ventas Full a Drive | lun–vie 06:30 | `pipeline.yml` |

Los nombres de los workflows (`manager-descargas.yml`, `pipeline.yml`) **no** se cambiaron:
están escritos en Supabase (`automatizacion.programa()`, `automatizacion.workflows_manual`)
y en los dashboards (`ActualizarDatos.montar({ workflow: ... })`).

## Archivos

- `00_pipeline_completo.py`: orquestador (8 pasos, ~11 min en GitHub Actions).
- `descargar_backup_manager.py`, `restaurar_y_extraer.py`: bajan y restauran el `.bak`.
- `ConsultasSQL/*.sql`: consultas que se corren contra la base restaurada (SQL Server), una por tabla de Supabase.
- `bulk_sync_supabase.py`, `sync_supabase.py`, `sync_nv_pendientes.py`, `sync_facturacion_periodo.py`, `sync_stock_productos.py`: cargas a Supabase.
- `subir_a_drive.py`: Excel de Ventas Full a Google Drive (`CONFIGURAR_GOOGLE_DRIVE.md`).
- `supabase/*.sql`: vistas y tablas de Supabase que dependen de estas cargas (se aplican a mano).
- `ejecutar_pipeline.bat`: entrada antigua del Programador de tareas de Windows (`C:\Scripts\BackupManager`); ya no se usa.
- `requirements.txt` está en UTF-16 (se ve raro en `cat`, pip lo lee bien).

Secrets del workflow: `SQL_SA_PASSWORD`, `MANAGER_USER`, `MANAGER_PASSWORD`, `SUPABASE_DB_URL`,
`SUPABASE_SERVICE_KEY`, `GOOGLE_CREDENTIALS_JSON`.
