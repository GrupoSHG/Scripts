-- Licitaciones de obras de Mercado Público relevantes para M5 Industrial.
-- La llena M5_Systems/mercado-publico/descarga_diaria.py --supabase (service_role, upsert por codigo_externo).
-- La lee la página licitaciones.html del sitio M5 Proyectos (GrupoSHG_Systems/M5_Systems/proyectos).
-- Se aplica a mano (SQL Editor o `supabase db query --linked -f`); es idempotente.

create table if not exists m5.licitaciones_mp (
  codigo_externo    text primary key,
  nombre            text not null,
  organismo         text,
  region            text,
  comuna            text,
  codigo_estado     int,
  estado            text,
  tipo              text,
  fecha_publicacion timestamptz,
  fecha_cierre      timestamptz,
  monto_estimado    numeric,
  moneda            text,
  url_ficha         text,
  palabras_clave    text[] not null default '{}',
  fecha_captura     timestamptz not null default now(),   -- primera vez que se capturó (el upsert no la envía)
  actualizado       timestamptz not null default now()    -- última corrida que la tocó
);

create index if not exists licitaciones_mp_cierre_idx on m5.licitaciones_mp (fecha_cierre);
create index if not exists licitaciones_mp_estado_idx on m5.licitaciones_mp (codigo_estado);

comment on table m5.licitaciones_mp is
  'Licitaciones de obras de Mercado Público (ChileCompra) filtradas por palabras clave. Fuente: Scripts/M5_Systems/mercado-publico.';

-- Acceso: solo usuarios con sesión leen; escribe solo service_role (el proceso diario).
alter table m5.licitaciones_mp enable row level security;
revoke all on m5.licitaciones_mp from anon, public;
grant select on m5.licitaciones_mp to authenticated;
grant all on m5.licitaciones_mp to service_role;

drop policy if exists lectura_autenticados on m5.licitaciones_mp;
create policy lectura_autenticados on m5.licitaciones_mp for select to authenticated using (true);

-- Igual que el resto de las tablas (accesos/clientes_m5.sql): un cliente externo de M5 no la ve.
drop policy if exists sin_clientes_externos on m5.licitaciones_mp;
create policy sin_clientes_externos on m5.licitaciones_mp as restrictive for all to authenticated
  using (coalesce(shg_dashboards.rol_actual(), '') <> 'cliente');

select count(*) as filas, count(*) filter (where codigo_estado = 5) as publicadas from m5.licitaciones_mp;
