-- Obras adjudicadas en Mercado Público (datos públicos) para la pestaña "Adjudicadas MP" del Cockpit
-- Comercial (GrupoSHG_Systems/cockpit-comercial-web/tabs/tab-adjudicadas.js), que muestra los últimos 14 días.
-- La llena M5_Systems/licitaciones-m5 (adjudicadas.py, al final del comando diario) con el rol licitaciones_m5.
-- Se aplica a mano (SQL Editor o `supabase --workdir <tmp> db query --linked -f`); es idempotente.
-- Requiere licitaciones_mp_evaluacion.sql (crea el rol licitaciones_m5).

-- 1. Una licitación adjudicada por fila. Del adjudicado se guardan RUT y razón social solo si es empresa
--    (RUT desde 50.000.000); una persona natural queda como "Persona natural" (adjudicadas.py).
create table if not exists m5.licitaciones_adjudicadas (
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
  es_obra              boolean not null,     -- algún ítem en rubro de construcción (UNSPSC 72, 30 o 95)
  actualizado          timestamptz,
  cargado_en           timestamptz not null default now()
);
create index if not exists licitaciones_adjudicadas_fecha_idx
  on m5.licitaciones_adjudicadas (fecha_adjudicacion desc) where es_obra;
create index if not exists licitaciones_adjudicadas_cargado_idx on m5.licitaciones_adjudicadas (cargado_en);

comment on table m5.licitaciones_adjudicadas is
  'Licitaciones adjudicadas de Mercado Público preseleccionadas como obras (es_obra = rubro de construcción). '
  'Fuente: Scripts/M5_Systems/licitaciones-m5 (adjudicadas.py). La lee el Cockpit Comercial.';

-- 2. Acceso: el equipo con sesión lee; el proceso (rol licitaciones_m5) inserta y actualiza; nadie borra.
--    Los vendedores quedan fuera por la política que el event trigger de accesos/vendedor_solo_lo_suyo.sql
--    agrega a toda tabla nueva de m5.
alter table m5.licitaciones_adjudicadas enable row level security;
revoke all on m5.licitaciones_adjudicadas from anon, public;
grant select on m5.licitaciones_adjudicadas to authenticated;
grant select, insert, update on m5.licitaciones_adjudicadas to licitaciones_m5;

drop policy if exists lectura_autenticados on m5.licitaciones_adjudicadas;
create policy lectura_autenticados on m5.licitaciones_adjudicadas for select to authenticated using (true);
drop policy if exists proceso_licitaciones_m5 on m5.licitaciones_adjudicadas;
create policy proceso_licitaciones_m5 on m5.licitaciones_adjudicadas for all to licitaciones_m5
  using (true) with check (true);

-- Igual que el resto de las tablas de m5 (accesos/clientes_m5.sql): un cliente externo de M5 no la ve.
drop policy if exists sin_clientes_externos on m5.licitaciones_adjudicadas;
create policy sin_clientes_externos on m5.licitaciones_adjudicadas as restrictive for all to authenticated
  using ((select coalesce(shg_dashboards.rol_actual(), '')) <> 'cliente');

select count(*) as filas, count(*) filter (where es_obra) as obras from m5.licitaciones_adjudicadas;
