-- ============================================================================
-- Seguridad, fase 1: cerrar los accesos anónimos que ningún sistema usa
-- ============================================================================
-- Diagnóstico del 05/10/2026 (proyecto ffxopvzxyeacpbtxuagu):
--  * Siete tablas de shg_dashboards (usuarios con PIN, nvs, ocs, oc_items,
--    proveedores, proveedor_contactos, categorias_umbral) tenían la política
--    "anon full access" heredada del sitio gestion-ordenes-compra, que apuntaba a
--    otro proyecto Supabase (ya eliminado) y hoy responde 404. Nadie las lee ni
--    escribe con la clave publicable; proveedores la escribe
--    backup-manager/sync_supabase.py con la clave de servicio (no usa políticas).
--  * Siete tablas de shg_dashboards (asistencia, facturas, gastos, centros_costo,
--    personas, iniciativas, facturacion) son la copia antigua de la app CyS, que
--    hoy trabaja en el schema app_cys. Tenían "Lectura pública" y, tres de ellas,
--    "Escritura pública".
--  * Varias funciones SECURITY DEFINER eran ejecutables por anon.
-- Este script no afecta a ningún dashboard, robot ni backend: se puede correr de
-- inmediato en el SQL Editor. La fase 2 (seguridad_anon_fase2.sql) sí requiere
-- desplegar código antes.
-- ============================================================================
begin;

-- 1) Tablas heredadas del sitio de órdenes de compra
drop policy if exists "anon full access" on shg_dashboards.usuarios;
drop policy if exists "anon full access" on shg_dashboards.nvs;
drop policy if exists "anon full access" on shg_dashboards.ocs;
drop policy if exists "anon full access" on shg_dashboards.oc_items;
drop policy if exists "anon full access" on shg_dashboards.proveedores;
drop policy if exists "anon full access" on shg_dashboards.proveedor_contactos;
drop policy if exists "anon full access" on shg_dashboards.categorias_umbral;
-- proveedores queda legible para usuarios con sesión (por si un dashboard la usa)
create policy "lectura_autenticados" on shg_dashboards.proveedores
  for select to authenticated using (true);

-- 2) Copia antigua de la app CyS dentro de shg_dashboards
drop policy if exists "Escritura pública" on shg_dashboards.asistencia;
drop policy if exists "Escritura pública" on shg_dashboards.facturas;
drop policy if exists "Escritura pública" on shg_dashboards.gastos;
drop policy if exists "Lectura pública" on shg_dashboards.asistencia;
drop policy if exists "Lectura pública" on shg_dashboards.facturas;
drop policy if exists "Lectura pública" on shg_dashboards.gastos;
drop policy if exists "Lectura pública" on shg_dashboards.centros_costo;
drop policy if exists "Lectura pública" on shg_dashboards.personas;
drop policy if exists "Lectura pública" on shg_dashboards.iniciativas;
drop policy if exists "Lectura pública" on shg_dashboards.facturacion;

-- 3) Sin privilegios para anon en esas 14 tablas (defensa adicional a RLS)
revoke all on table
  shg_dashboards.usuarios, shg_dashboards.nvs, shg_dashboards.ocs,
  shg_dashboards.oc_items, shg_dashboards.proveedores,
  shg_dashboards.proveedor_contactos, shg_dashboards.categorias_umbral,
  shg_dashboards.asistencia, shg_dashboards.facturas, shg_dashboards.gastos,
  shg_dashboards.centros_costo, shg_dashboards.personas,
  shg_dashboards.iniciativas, shg_dashboards.facturacion
from anon;

-- 4) Funciones SECURITY DEFINER que anon no necesita ejecutar. Las funciones de
--    trigger siguen disparándose igual (Postgres no exige EXECUTE al rol que
--    hace el INSERT/UPDATE); solo dejan de ser llamables por /rest/v1/rpc.
revoke execute on function shg_dashboards.fn_recalcular_facturacion(uuid, date) from anon;
revoke execute on function shg_dashboards.fn_trigger_recalcular_facturacion() from anon;
revoke execute on function public.fn_recalcular_facturacion(uuid, date) from anon;
revoke execute on function public.fn_trigger_asistencia_facturacion() from anon;
revoke execute on function public.fn_trigger_gastos_facturacion() from anon;
revoke execute on function app_cys.fn_recalcular_facturacion_periodo(uuid, date, date) from anon;
revoke execute on function app_cys.fn_trigger_recalcular_facturacion_periodo() from anon;
revoke execute on function hea.current_role() from anon;

commit;

-- Verificación: no debe quedar ninguna política que incluya a anon en estas tablas
-- select schemaname, tablename, policyname, roles from pg_policies
--  where schemaname = 'shg_dashboards' and (roles = '{public}' or 'anon' = any(roles))
--    and tablename in ('usuarios','nvs','ocs','oc_items','proveedores','proveedor_contactos',
--                      'categorias_umbral','asistencia','facturas','gastos','centros_costo',
--                      'personas','iniciativas','facturacion');
