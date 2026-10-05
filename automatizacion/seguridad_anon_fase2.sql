-- ============================================================================
-- Seguridad, fase 2: ninguna tabla de negocio se lee con la clave publicable
-- ============================================================================
-- Hoy casi todo shg_dashboards (ventas_full, cxc, notas_de_venta, facturación,
-- stock...) es legible por cualquiera que tenga la clave publicable, que va en el
-- JavaScript de los dashboards. Lo mismo app_cys (sin RLS y con permisos de
-- escritura para anon) y hea.ots. Esta fase deja todo en "solo authenticated"
-- (sesión de admin-session.js) o clave de servicio.
--
-- ANTES DE CORRERLO, en este orden, o los dashboards se quedan sin datos:
--  1. En los 4 proyectos de Apps Script (cockpit-comercial, dashboard-produccion,
--     dashboard-finanzas, calendario-despachos): Configuración del proyecto →
--     Propiedades del script → agregar SUPABASE_SERVICE_KEY = clave service_role
--     (la legacy, formato JWT "eyJ…"; las sb_secret_ nuevas devuelven 401 desde
--     Apps Script). Luego `clasp push` de los 4 con el código de la rama
--     worktree-seguridad-anon de GrupoSHG_Systems.
--  2. Desplegar trazabilidad-nv y app-cys desde esa misma rama (el merge a main
--     lo hace Netlify): ambos crean el cliente con el storageKey de admin-session.
--  3. En GrupoSHG/Scripts, mergear la rama worktree-seguridad-anon: monitoreo.py
--     usa el secret SUPABASE_SERVICE_KEY y bulk_sync_supabase.py crea las
--     políticas "to authenticated" (si no, el pipeline de las 06:30 las vuelve
--     a abrir al recrear las tablas).
-- Quedan abiertas a propósito: public.ultima_actualizacion (solo devuelve una hora,
-- la usan las páginas sin login) y la lectura del bucket de Storage "facturas"
-- (la app CyS muestra las fotos con getPublicUrl).
-- ============================================================================
begin;

-- 1) shg_dashboards: todas las políticas que incluían a anon pasan a authenticated
do $$
declare r record;
begin
  for r in
    select schemaname, tablename, policyname
      from pg_policies
     where schemaname = 'shg_dashboards'
       and (roles = '{public}' or 'anon' = any(roles))
  loop
    execute format('alter policy %I on %I.%I to authenticated',
                   r.policyname, r.schemaname, r.tablename);
  end loop;
end $$;

revoke all on all tables    in schema shg_dashboards from anon;   -- incluye la vista trazabilidad_nv
revoke all on all sequences in schema shg_dashboards from anon;
revoke execute on function shg_dashboards.ultima_carga_manager() from anon; -- monitoreo usa clave de servicio
alter default privileges for role postgres in schema shg_dashboards revoke all on tables from anon;
revoke usage on schema shg_dashboards from anon;

-- 2) hea: la app lee con sesión y el Cockpit con clave de servicio
drop policy if exists ots_select_anon on hea.ots;
revoke all on all tables    in schema hea from anon;
revoke all on all sequences in schema hea from anon;
revoke usage on schema hea from anon;

-- 3) app_cys: RLS activado, solo usuarios con sesión. cys-asistencia-sync y la
--    Edge Function procesar-factura usan service_role, que no pasa por RLS.
do $$
declare t text;
begin
  foreach t in array array['centros_costo','personas','iniciativas','asistencia',
                           'gastos','facturas','facturacion']
  loop
    execute format('alter table app_cys.%I enable row level security', t);
    execute format('drop policy if exists autenticados on app_cys.%I', t);
    execute format('create policy autenticados on app_cys.%I for all to authenticated using (true) with check (true)', t);
  end loop;
end $$;
revoke all on all tables    in schema app_cys from anon;
revoke all on all sequences in schema app_cys from anon;
revoke usage on schema app_cys from anon;

-- 4) Storage, bucket facturas: subir y borrar solo con sesión; la lectura sigue pública
alter policy "Escritura pública facturas storage" on storage.objects to authenticated;
alter policy "Borrado público facturas storage"   on storage.objects to authenticated;

commit;

-- Verificación (debe devolver 0 filas):
-- select schemaname, tablename, policyname, roles from pg_policies
--  where schemaname in ('shg_dashboards','app_cys','hea')
--    and (roles = '{public}' or 'anon' = any(roles));
-- Y comprobar: Cockpit (resumen + tarjeta HEA), Producción, Finanzas (CxC),
-- Calendario, Trazabilidad NV, App CyS (guardar un gasto) y el monitoreo.
