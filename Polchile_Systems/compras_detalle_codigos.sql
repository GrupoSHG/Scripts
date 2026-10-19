-- =====================================================================
-- compras_detalle_codigos.sql  (se aplica a mano en el SQL Editor de Supabase)
-- Proyecto ffxopvzxyeacpbtxuagu, esquema shg_dashboards. Idempotente.
--
-- Códigos de artículo y cuentas contables que finanzas asigna, línea por línea,
-- en el detalle de cada factura de compra de la pantalla RCV · SII del
-- Dashboard Finanzas (botón "Guardar códigos" en rcv.js). Así no se pierden al
-- recargar, los ve todo el equipo y la importación masiva a Manager
-- (rcv-manager.js) los usa al armar el archivo.
--
-- La línea es la posición del ítem en el XML del DTE (1, 2, 3...), el mismo
-- orden que devuelve la Edge Function rcv-sii en /dte/folio.
-- Al guardar, cada par código → cuenta también se memoriza en
-- shg_dashboards.codigos_cuenta (ver plan_cuentas.sql), para autocompletar las
-- próximas facturas con ese código.
-- Escriben solo usuarios con acceso a Finanzas (public.puede_ver).
-- =====================================================================

create table if not exists shg_dashboards.compras_detalle_codigos (
    empresa         text        not null default 'polchile',
    rut             text        not null,      -- RUT del proveedor, sin puntos, con guión, mayúsculas
    tipo_dte        int         not null,      -- 33, 34, 46, 61...
    folio           bigint      not null,
    linea           int         not null,      -- posición del ítem en el XML (desde 1)
    descripcion     text,
    cantidad        numeric,
    monto           numeric,
    codigo          text,                      -- código de artículo de Manager
    cuenta          text,                      -- cuenta contable (plan_cuentas.codigo)
    actualizado_por text,
    actualizado_en  timestamptz not null default now(),
    primary key (empresa, rut, tipo_dte, folio, linea)
);
create index if not exists compras_detalle_codigos_folio_idx on shg_dashboards.compras_detalle_codigos (folio);

alter table shg_dashboards.compras_detalle_codigos enable row level security;
drop policy if exists compras_detalle_codigos_lectura on shg_dashboards.compras_detalle_codigos;
create policy compras_detalle_codigos_lectura on shg_dashboards.compras_detalle_codigos
  for select to authenticated using (public.puede_ver('finanzas') is not null);
revoke all on shg_dashboards.compras_detalle_codigos from anon;
grant select on shg_dashboards.compras_detalle_codigos to authenticated;
grant all on shg_dashboards.compras_detalle_codigos to service_role;

-- Guarda los códigos de una factura. p_items: [{linea, descripcion, cantidad, monto, codigo, cuenta}, ...]
-- Reemplaza las líneas de esa factura (las que no vienen se borran) y memoriza código → cuenta.
create or replace function public.guardar_codigos_factura(p_empresa text, p_rut text, p_tipo_dte int, p_folio bigint, p_items jsonb)
returns int language plpgsql security definer set search_path = shg_dashboards, public as $$
declare
  v_usuario text := coalesce(auth.jwt() ->> 'email', 'usuario');
  v_empresa text := coalesce(nullif(p_empresa, ''), 'polchile');
  v_rut     text := upper(replace(replace(trim(coalesce(p_rut, '')), '.', ''), ' ', ''));
  v_n int;
begin
  if public.puede_ver('finanzas') is null then
    raise exception 'Sin acceso a Finanzas';
  end if;
  if v_rut = '' or p_folio is null or p_tipo_dte is null then
    raise exception 'Faltan RUT, tipo o folio de la factura';
  end if;

  delete from shg_dashboards.compras_detalle_codigos
   where empresa = v_empresa and rut = v_rut and tipo_dte = p_tipo_dte and folio = p_folio;

  insert into shg_dashboards.compras_detalle_codigos
    (empresa, rut, tipo_dte, folio, linea, descripcion, cantidad, monto, codigo, cuenta, actualizado_por, actualizado_en)
  select v_empresa, v_rut, p_tipo_dte, p_folio, (i->>'linea')::int,
         left(i->>'descripcion', 200), nullif(i->>'cantidad', '')::numeric, nullif(i->>'monto', '')::numeric,
         nullif(trim(i->>'codigo'), ''), nullif(trim(i->>'cuenta'), ''), v_usuario, now()
  from jsonb_array_elements(p_items) i
  where coalesce(i->>'linea', '') <> ''
    and (nullif(trim(i->>'codigo'), '') is not null or nullif(trim(i->>'cuenta'), '') is not null);
  get diagnostics v_n = row_count;

  insert into shg_dashboards.codigos_cuenta as cc (empresa, codigo_item, cuenta, descripcion, actualizado_por, actualizado_en)
  select distinct on (trim(i->>'codigo'))
         v_empresa, trim(i->>'codigo'), trim(i->>'cuenta'), left(i->>'descripcion', 200), v_usuario, now()
  from jsonb_array_elements(p_items) i
  where nullif(trim(i->>'codigo'), '') is not null and nullif(trim(i->>'cuenta'), '') is not null
  on conflict (empresa, codigo_item) do update set
    cuenta = excluded.cuenta, descripcion = coalesce(excluded.descripcion, cc.descripcion),
    actualizado_por = excluded.actualizado_por, actualizado_en = excluded.actualizado_en;

  return v_n;
end $$;

revoke all on function public.guardar_codigos_factura(text, text, int, bigint, jsonb) from public, anon;
grant execute on function public.guardar_codigos_factura(text, text, int, bigint, jsonb) to authenticated;

-- Comprobación
-- select folio, linea, codigo, cuenta, actualizado_por, actualizado_en from shg_dashboards.compras_detalle_codigos order by actualizado_en desc limit 20;
