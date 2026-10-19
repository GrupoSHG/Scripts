-- =====================================================================
-- rcv_consultas.sql  (se aplica a mano en el SQL Editor de Supabase)
-- Proyecto ffxopvzxyeacpbtxuagu, esquema shg_dashboards. Idempotente.
--
-- Guarda el resultado de cada consulta del Registro de Compras y Ventas del
-- SII (SimpleAPI) por empresa y período, para no volver a gastar consultas:
-- el plan de SimpleAPI permite 30 al mes y cada "Consultar RCV" gasta dos
-- (compras y ventas). La Edge Function rcv-sii (GrupoSHG_Systems,
-- Polchile_Systems/area-finanzas-rcv-backend) responde /rcv desde aquí y solo
-- llama al SII si el período no está guardado o si se pide ?refrescar=1
-- (botón "Actualizar desde el SII" de la pantalla RCV · SII).
--
-- Escribe solo la Edge Function (service_role). Leen los usuarios con acceso
-- a Finanzas.
-- =====================================================================

create table if not exists shg_dashboards.rcv_consultas (
    empresa         text        not null,          -- polchile | m5
    periodo         text        not null,          -- YYYY-MM
    compra          jsonb       not null default '[]'::jsonb,   -- documentos normalizados (como los entrega /rcv)
    venta           jsonb       not null default '[]'::jsonb,
    resumen_compras jsonb       not null default '[]'::jsonb,
    resumen_ventas  jsonb       not null default '[]'::jsonb,
    n_compras       int         not null default 0,
    n_ventas        int         not null default 0,
    consultado_en   timestamptz not null default now(),     -- última vez que se pidió al SII
    consultado_por  text,
    n_consultas_sii int         not null default 1,         -- cuántas veces se consultó este período al SII
    primary key (empresa, periodo)
);

alter table shg_dashboards.rcv_consultas enable row level security;
drop policy if exists rcv_consultas_lectura on shg_dashboards.rcv_consultas;
create policy rcv_consultas_lectura on shg_dashboards.rcv_consultas
  for select to authenticated using (public.puede_ver('finanzas') is not null);
revoke all on shg_dashboards.rcv_consultas from anon;
grant select on shg_dashboards.rcv_consultas to authenticated;
grant all on shg_dashboards.rcv_consultas to service_role;

-- Comprobación
-- select empresa, periodo, n_compras, n_ventas, consultado_en, consultado_por, n_consultas_sii
--   from shg_dashboards.rcv_consultas order by empresa, periodo desc;
