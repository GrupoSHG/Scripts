-- Obras adjudicadas en Mercado Público (datos públicos) como oportunidades de negocio para Polchile.
-- La llena Polchile_Systems/sync_adjudicadas_mp.py (workflow adjudicadas-mp-polchile.yml, con la service key) y la
-- lee la pestaña "Adjudicadas MP" del Cockpit Comercial (GrupoSHG_Systems/cockpit-comercial-web/tabs/tab-adjudicadas.js).
-- Se aplica a mano (SQL Editor o `supabase --workdir <tmp> db query --linked -f`); es idempotente.

-- 1. Una licitación adjudicada por fila. Del adjudicado se guardan RUT y razón social solo si es empresa
--    (RUT desde 50.000.000); una persona natural queda como "Persona natural".
create table if not exists polchile_crm.adjudicadas_mp (
  codigo_externo       text primary key,
  nombre               text not null,
  organismo            text,
  region               text,
  comuna               text,
  tipo                 text,                 -- LE, LP, LR, L1...
  moneda               text,                 -- CLP, UF, USD...
  monto_estimado       numeric,              -- solo si el organismo lo publicó
  monto_adjudicado     numeric,              -- suma de cantidad x monto unitario de los ítems, en `moneda`, sin IVA
  fecha_adjudicacion   timestamptz,
  numero_oferentes     int,
  url_acta             text,
  url_ficha            text,
  adjudicatarios       jsonb not null default '[]'::jsonb,  -- [{rut, nombre, monto, items}], mayor monto primero
  proveedor_principal  text,
  rut_principal        text,
  categorias           text[] not null default '{}',        -- UNSPSC de los ítems
  palabras_clave       text[] not null default '{}',        -- las del nombre que la preseleccionaron
  interes              text not null check (interes in ('alto', 'obra')),  -- alto = techumbre, cubierta, panel, galpón...
  es_obra              boolean not null,     -- algún ítem en rubro de construcción (UNSPSC 72, 30 o 95)
  actualizado          timestamptz,
  cargado_en           timestamptz not null default now()
);
create index if not exists adjudicadas_mp_fecha_idx on polchile_crm.adjudicadas_mp (fecha_adjudicacion desc) where es_obra;
create index if not exists adjudicadas_mp_cargado_idx on polchile_crm.adjudicadas_mp (cargado_en);

comment on table polchile_crm.adjudicadas_mp is
  'Licitaciones de obras adjudicadas en Mercado Público: posibles clientes de Polchile (las constructoras que las '
  'ganaron). Fuente: Scripts/Polchile_Systems/sync_adjudicadas_mp.py. La lee el Cockpit Comercial.';

-- 2. Acceso: el equipo con sesión lee; escribe solo el sync (service_role, que se salta la RLS).
--    Los vendedores quedan fuera por la política que el event trigger de accesos/vendedor_solo_lo_suyo.sql
--    (GrupoSHG_Systems) agrega a toda tabla nueva de polchile_crm.
alter table polchile_crm.adjudicadas_mp enable row level security;
revoke all on polchile_crm.adjudicadas_mp from anon, public;
grant select on polchile_crm.adjudicadas_mp to authenticated;
grant select, insert, update on polchile_crm.adjudicadas_mp to service_role;  -- sin esto la primera corrida (29/10/2026) falló con 42501

drop policy if exists lectura_autenticados on polchile_crm.adjudicadas_mp;
create policy lectura_autenticados on polchile_crm.adjudicadas_mp for select to authenticated using (true);
-- Un cliente externo de M5 (portal de clientes) no la ve.
drop policy if exists sin_clientes_externos on polchile_crm.adjudicadas_mp;
create policy sin_clientes_externos on polchile_crm.adjudicadas_mp as restrictive for all to authenticated
  using ((select coalesce(shg_dashboards.rol_actual(), '')) <> 'cliente');

-- 3. Disparo nocturno a las 23:20: automatizacion/adjudicadas_mp_programa.sql.

select count(*) as filas, count(*) filter (where es_obra) as obras from polchile_crm.adjudicadas_mp;
