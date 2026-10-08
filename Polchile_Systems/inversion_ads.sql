-- ============================================================================
-- Inversión publicitaria (Google Ads, Meta Ads) en Supabase, schema polchile_crm
-- ============================================================================
-- La llena el workflow ads-polchile-sync (Polchile_Systems/sync_ads_polchile.py) a partir de
-- la hoja de Google que escribe el script de Google Ads (Polchile_Systems/google_ads_script.js);
-- la pestaña "meta" de esa misma hoja se llena a mano. Cómo se configura: INVERSION_ADS.md.
--
-- La lee polchile_crm.resumen_dashboard (GrupoSHG_Systems/Polchile_Systems/comercial-crm/
-- resumen_dashboard.sql) para la inversión, el costo por lead y el retorno de la pestaña
-- CRM Polchile del Cockpit y del dashboard CRM Comercial.
--
-- Se aplica a mano en el SQL Editor (idempotente), ANTES de resumen_dashboard.sql.
-- ============================================================================

create table if not exists polchile_crm.inversion_ads (
  plataforma     text not null,                 -- 'google' | 'meta'
  fecha          date not null,
  campana_id     text not null default '',      -- id de la campaña en la plataforma ('' en cargas manuales)
  campana        text,
  costo          numeric not null default 0,    -- CLP, tal como lo informa la plataforma (sin IVA)
  impresiones    bigint  not null default 0,
  clics          bigint  not null default 0,
  conversiones   numeric not null default 0,    -- conversiones que cuenta la plataforma (no son leads del CRM)
  actualizado_en timestamptz not null default now(),
  primary key (plataforma, fecha, campana_id),
  constraint inversion_ads_plataforma_chk check (plataforma in ('google', 'meta'))
);
create index if not exists inversion_ads_fecha_idx on polchile_crm.inversion_ads (fecha);

-- Solo lectura con sesión, como el resto del schema (el service_role escribe a través del RPC).
alter table polchile_crm.inversion_ads enable row level security;
grant select on polchile_crm.inversion_ads to authenticated;
drop policy if exists lectura_autenticados on polchile_crm.inversion_ads;
create policy lectura_autenticados on polchile_crm.inversion_ads for select to authenticated using (true);

-- Carga de una plataforma: reemplaza todas las fechas entre la mínima y la máxima del lote.
-- Google Ads ajusta el gasto de los últimos días (clics inválidos, conversiones tardías), por
-- eso el script manda cada día una ventana completa y aquí se borra y se vuelve a insertar.
-- Las fechas fuera de la ventana no se tocan, así la historia se acumula en Supabase aunque
-- la hoja solo conserve los últimos meses.
-- Filas: [{fecha, campana_id, campana, costo, impresiones, clics, conversiones}, ...]
create or replace function polchile_crm.cargar_inversion_ads(p_plataforma text, p_filas jsonb)
returns jsonb language plpgsql security definer set search_path = polchile_crm, pg_temp as $$
declare d1 date; d2 date; n int; total numeric;
begin
  if p_plataforma not in ('google', 'meta') then
    raise exception 'Plataforma desconocida: % (se aceptan google y meta)', p_plataforma;
  end if;
  select min((f->>'fecha')::date), max((f->>'fecha')::date), sum(coalesce((f->>'costo')::numeric, 0))
    into d1, d2, total
  from jsonb_array_elements(coalesce(p_filas, '[]'::jsonb)) f;
  if d1 is null then
    return jsonb_build_object('plataforma', p_plataforma, 'filas', 0);
  end if;
  delete from inversion_ads where plataforma = p_plataforma and fecha between d1 and d2;
  insert into inversion_ads (plataforma, fecha, campana_id, campana, costo, impresiones, clics, conversiones)
  select p_plataforma, (f->>'fecha')::date, coalesce(f->>'campana_id', ''),
         max(nullif(trim(f->>'campana'), '')),
         sum(coalesce((f->>'costo')::numeric, 0)),
         sum(coalesce((f->>'impresiones')::bigint, 0)),
         sum(coalesce((f->>'clics')::bigint, 0)),
         sum(coalesce((f->>'conversiones')::numeric, 0))
  from jsonb_array_elements(p_filas) f
  group by 2, 3;
  get diagnostics n = row_count;
  return jsonb_build_object('plataforma', p_plataforma, 'desde', d1, 'hasta', d2, 'filas', n, 'costo', total);
end $$;

revoke all on function polchile_crm.cargar_inversion_ads(text, jsonb) from public, anon, authenticated;
grant execute on function polchile_crm.cargar_inversion_ads(text, jsonb) to service_role;
