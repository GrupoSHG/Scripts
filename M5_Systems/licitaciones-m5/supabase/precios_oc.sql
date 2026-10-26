-- Precios de referencia de materiales desde órdenes de compra de Mercado Público (datos públicos).
-- La llena M5_Systems/licitaciones-m5 (precios_oc.py + normalizacion.py) con el rol licitaciones_m5;
-- la lee el dashboard de M5 (con sesión) para estimar costos de materiales de las licitaciones.
-- Se aplica a mano (SQL Editor o `supabase --workdir <tmp> db query --linked -f`); es idempotente.
-- Requiere licitaciones_mp_evaluacion.sql (crea el rol licitaciones_m5).

-- 1. Un ítem de orden de compra normalizado por fila. Sin datos de contactos ni del proveedor.
create table if not exists m5.precios_oc_items (
  oc                        text not null,
  correlativo               int  not null,
  fecha_envio               timestamptz,
  region                    text,
  producto_mercado_publico  text,
  codigo_categoria          bigint,            -- UNSPSC, tal como lo puso el comprador
  especificacion_comprador  text,
  cantidad                  numeric,
  precio_presentacion       numeric not null,  -- PrecioNeto de la OC: por unidad comprada, sin IVA, CLP
  es_material_construccion  boolean not null,
  material                  text,
  especificacion            text,
  presentacion              text,
  contenido                 numeric,           -- tal como está escrito (300 ml, 25 kg...)
  unidad_contenido          text,
  contenido_base            numeric,           -- convertido por el código (0,3 litro, 25 kg...)
  unidad_base               text check (unidad_base in ('unidad', 'kg', 'm', 'm2', 'm3', 'litro')),
  precio_unidad_base        numeric,           -- precio_presentacion / contenido_base
  confianza                 text not null check (confianza in ('alta', 'media', 'baja')),
  modelo                    text,
  cargado_en                timestamptz not null default now(),
  primary key (oc, correlativo)
);
create index if not exists precios_oc_items_material_idx on m5.precios_oc_items (material, presentacion);
create index if not exists precios_oc_items_fecha_idx on m5.precios_oc_items (fecha_envio);

comment on table m5.precios_oc_items is
  'Ítems de órdenes de compra de Mercado Público normalizados con Claude (material, presentación, unidad). '
  'Precios del comprador público, no de M5. Fuente: Scripts/M5_Systems/licitaciones-m5.';

-- 2. Precio de referencia por material + especificación + presentación: últimos 90 días, solo
--    materiales de construcción con confianza alta o media. La mediana resiste los precios absurdos.
create or replace view m5.precios_referencia with (security_invoker = true) as
select material,
       coalesce(especificacion, '') as especificacion,
       presentacion,
       count(*)                                                              as n,
       percentile_cont(0.5)  within group (order by precio_presentacion)    as mediana_presentacion,
       percentile_cont(0.25) within group (order by precio_presentacion)    as p25_presentacion,
       percentile_cont(0.75) within group (order by precio_presentacion)    as p75_presentacion,
       max(unidad_base)                                                      as unidad_base,
       percentile_cont(0.5)  within group (order by precio_unidad_base)     as mediana_unidad_base,
       min(fecha_envio)                                                      as desde,
       max(fecha_envio)                                                      as hasta
  from m5.precios_oc_items
 where es_material_construccion
   and confianza in ('alta', 'media')
   and material is not null and presentacion is not null
   and fecha_envio >= now() - interval '90 days'
 group by 1, 2, 3;

-- 3. Acceso: el equipo con sesión lee; el proceso (rol licitaciones_m5) inserta y actualiza; nadie borra.
alter table m5.precios_oc_items enable row level security;
revoke all on m5.precios_oc_items from anon, public;
grant select on m5.precios_oc_items to authenticated;
grant select, insert, update on m5.precios_oc_items to licitaciones_m5;
revoke all on m5.precios_referencia from anon, public;
grant select on m5.precios_referencia to authenticated, licitaciones_m5;

drop policy if exists lectura_autenticados on m5.precios_oc_items;
create policy lectura_autenticados on m5.precios_oc_items for select to authenticated using (true);
drop policy if exists proceso_licitaciones_m5 on m5.precios_oc_items;
create policy proceso_licitaciones_m5 on m5.precios_oc_items for all to licitaciones_m5 using (true) with check (true);

-- Igual que el resto de las tablas de m5 (accesos/clientes_m5.sql): un cliente externo de M5 no la ve.
drop policy if exists sin_clientes_externos on m5.precios_oc_items;
create policy sin_clientes_externos on m5.precios_oc_items as restrictive for all to authenticated
  using (coalesce(shg_dashboards.rol_actual(), '') <> 'cliente');

select count(*) as items from m5.precios_oc_items;
