-- ============================================================================
-- importaciones.sql — lectura de shg_dashboards.importaciones solo con sesión
-- ============================================================================
-- La tabla la crea el pipeline diario (bulk_sync_supabase.py) a partir de
-- ConsultasSQL/Importaciones.sql; este script se aplica UNA vez, después de la
-- primera corrida del pipeline que la cree, en el SQL Editor de Supabase.
-- Las corridas siguientes solo hacen TRUNCATE + COPY (las columnas no cambian),
-- así que las políticas se conservan. Si algún día cambian las columnas de la
-- consulta, el cargador recrea la tabla y hay que volver a correr esto.
--
-- Quién la lee: la sección "Importaciones · histórico de órdenes de compra" del
-- Dashboard Producción (GrupoSHG_Systems/Polchile_Systems/dashboard-produccion-web),
-- con el cliente supabase-js de la sesión (rol authenticated).
-- ============================================================================
begin;

alter table shg_dashboards.importaciones enable row level security;

drop policy if exists "lectura_autenticados" on shg_dashboards.importaciones;
create policy "lectura_autenticados" on shg_dashboards.importaciones
  for select to authenticated using (true);

revoke all on table shg_dashboards.importaciones from anon;
grant select on table shg_dashboards.importaciones to authenticated;

commit;

select familia, estado, count(*) filas, min(fecha) desde, max(fecha) hasta
from shg_dashboards.importaciones group by 1, 2 order by 1, 2;
