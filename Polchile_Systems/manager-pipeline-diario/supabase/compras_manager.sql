-- =====================================================================
-- compras_manager.sql  (se aplica a mano en el SQL Editor de Supabase)
-- Proyecto ffxopvzxyeacpbtxuagu, esquema shg_dashboards. Idempotente.
--
-- Acompaña a manager-pipeline-diario/ConsultasSQL/Compras_Manager.sql:
-- espejo diario de los documentos de compra de Manager (FAC, GDR, NCC)
-- con sus líneas, para que la pantalla RCV · SII del Dashboard Finanzas
-- haga el calce con el Registro de Compras del SII y arme el archivo de
-- importación de las facturas que faltan (Abastecimiento > Menú de
-- Abastecimiento > Otros Procesos > Importar Doc Compras; formato Excel
-- 5.0/95 sin encabezados, 29 columnas, ver
-- https://ayudaerp.manager.cl/es/articles/6445866-importacion-de-documentos-de-compra).
--
--   1. compras_manager                 tabla espejo (la llena el pipeline).
--   2. compras_manager_docs            una fila por documento (para el calce).
--   3. compras_sugerencias_proveedor   último artículo / cuenta / centro de
--                                      costo / bodega usados con cada RUT.
--   4. compras_articulos               por artículo de gasto: cuenta, centro y
--                                      bodega más usados (autocompletar).
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Tabla. Mismas columnas, orden y tipos que infiere bulk_sync_supabase.py
--    desde Compras_Manager.sql: así el pipeline la vacía con TRUNCATE + COPY
--    y no intenta recrearla (un DROP fallaría por las vistas).
-- ---------------------------------------------------------------------
create table if not exists shg_dashboards.compras_manager (
    docto             text,
    tipodoc           bigint,
    num_docto         bigint,
    numreg            bigint,
    fecha             timestamp,
    fecha_vencimiento timestamp,
    rut               text,
    proveedor         text,
    es_electronico    bigint,
    nula              bigint,
    afecto            bigint,
    total_neto        double precision,
    total_exento      double precision,
    total_iva         double precision,
    total             double precision,
    moneda            text,
    sucursal          bigint,
    orden_compra      text,
    glosa             text,
    linea             bigint,
    articulo          text,
    descripcion       text,
    cantidad          double precision,
    precio_unitario   double precision,
    cuenta_contable   text,
    centro_costo      text,
    bodega            text
);
alter table shg_dashboards.compras_manager enable row level security;
drop policy if exists lectura_publica_compras_manager on shg_dashboards.compras_manager;
create policy lectura_publica_compras_manager on shg_dashboards.compras_manager for select to authenticated using (true);
revoke all on shg_dashboards.compras_manager from anon;
grant select on shg_dashboards.compras_manager to authenticated, service_role;
create index if not exists compras_manager_rut_num_idx on shg_dashboards.compras_manager (rut, num_docto);
create index if not exists compras_manager_fecha_idx on shg_dashboards.compras_manager (fecha);

-- ---------------------------------------------------------------------
-- 2. Una fila por documento. rut_norm: sin puntos, con guión, mayúsculas,
--    igual que el RUT que entrega el RCV del SII.
-- ---------------------------------------------------------------------
create or replace view shg_dashboards.compras_manager_docs as
select
    c.docto,
    max(c.tipodoc)                                  as tipodoc,
    c.num_docto,
    c.numreg,
    upper(replace(trim(c.rut), '.', ''))            as rut,
    max(c.proveedor)                                as proveedor,
    min(c.fecha)::date                              as fecha,
    min(c.fecha_vencimiento)::date                  as fecha_vencimiento,
    max(c.es_electronico)                           as es_electronico,
    max(c.nula)                                     as nula,
    max(c.afecto)                                   as afecto,
    max(c.total_neto)                               as total_neto,
    max(c.total_exento)                             as total_exento,
    max(c.total_iva)                                as total_iva,
    max(c.total)                                    as total,
    max(c.orden_compra)                             as orden_compra,
    max(c.glosa)                                    as glosa,
    count(*)                                        as n_lineas,
    (array_agg(c.articulo        order by c.linea))[1] as articulo,
    (array_agg(c.descripcion     order by c.linea))[1] as descripcion,
    (array_agg(c.cuenta_contable order by c.linea))[1] as cuenta_contable,
    (array_agg(c.centro_costo    order by c.linea))[1] as centro_costo,
    (array_agg(c.bodega          order by c.linea))[1] as bodega
from shg_dashboards.compras_manager c
group by c.docto, c.num_docto, c.numreg, upper(replace(trim(c.rut), '.', ''));

-- ---------------------------------------------------------------------
-- 3. Sugerencia por proveedor: cómo se registró su última factura (FAC).
-- ---------------------------------------------------------------------
create or replace view shg_dashboards.compras_sugerencias_proveedor as
with facturas as (
    select d.*
    from shg_dashboards.compras_manager_docs d
    where d.docto = 'FAC' and coalesce(d.nula, 0) = 0 and coalesce(d.articulo, '') <> ''
),
ultima as (
    select distinct on (rut) rut, proveedor, fecha, num_docto, articulo, descripcion, cuenta_contable, centro_costo, bodega, afecto, n_lineas
    from facturas
    order by rut, fecha desc, numreg desc
)
select
    u.rut,
    u.proveedor,
    u.fecha                       as ultima_fecha,
    u.num_docto                   as ultimo_num_docto,
    u.articulo,
    u.descripcion,
    u.cuenta_contable,
    u.centro_costo,
    u.bodega,
    u.afecto,
    u.n_lineas                    as ultima_n_lineas,
    (select count(*) from facturas f where f.rut = u.rut) as n_facturas
from ultima u;

-- ---------------------------------------------------------------------
-- 4. Por artículo de gasto: cuenta, centro de costo y bodega más usados.
-- ---------------------------------------------------------------------
create or replace view shg_dashboards.compras_articulos as
with lineas as (
    select articulo, descripcion, cuenta_contable, centro_costo, bodega
    from shg_dashboards.compras_manager
    where docto = 'FAC' and coalesce(nula, 0) = 0 and coalesce(articulo, '') <> ''
),
moda as (
    select articulo,
           mode() within group (order by nullif(descripcion, ''))     as descripcion,
           mode() within group (order by nullif(cuenta_contable, '')) as cuenta_contable,
           mode() within group (order by nullif(centro_costo, ''))    as centro_costo,
           mode() within group (order by nullif(bodega, ''))          as bodega,
           count(*)                                                   as n_lineas
    from lineas
    group by articulo
)
select * from moda;

revoke all on shg_dashboards.compras_manager_docs, shg_dashboards.compras_sugerencias_proveedor, shg_dashboards.compras_articulos from anon;
grant select on shg_dashboards.compras_manager_docs, shg_dashboards.compras_sugerencias_proveedor, shg_dashboards.compras_articulos to authenticated, service_role;

-- Comprobación
-- select count(*) from shg_dashboards.compras_manager_docs where docto = 'FAC' and fecha >= date_trunc('month', current_date);
-- select * from shg_dashboards.compras_sugerencias_proveedor order by n_facturas desc limit 20;
