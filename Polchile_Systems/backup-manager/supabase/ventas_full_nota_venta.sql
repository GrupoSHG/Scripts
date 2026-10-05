-- =====================================================================
-- ventas_full_nota_venta.sql  (se aplica a mano en el SQL Editor de Supabase)
-- Proyecto ffxopvzxyeacpbtxuagu, esquema shg_dashboards.
--
-- Acompaña al cambio de backup-manager/ConsultasSQL/Ventas_Full.sql, que
-- agrega a cada línea del Ventas Full la Nota de Venta de origen
-- (nota_venta) y, en las notas de crédito, la factura referenciada
-- (factura_ref).
--
-- 1. Agrega las dos columnas a shg_dashboards.ventas_full. No hace falta
--    para el pipeline diario (bulk_sync_supabase.py recrea la tabla si
--    cambian las columnas), pero sí para que el robot horario
--    (manager-descargas/cargar.py -> reemplazar_ventas_full) pueda
--    insertarlas desde ya: jsonb_populate_recordset ignora las claves que
--    no existen en la tabla.
-- 2. Reescribe la vista shg_dashboards.trazabilidad_nv para que lo
--    facturado y las notas de crédito salgan de ventas_full (el registro
--    real de facturación) y no de las guías de despacho. Mantiene los
--    mismos nombres y tipos de columna que la vista actual, así
--    trazabilidad-nv/index.html sigue funcionando sin cambios.
-- =====================================================================

alter table shg_dashboards.ventas_full
    add column if not exists nota_venta  bigint,
    add column if not exists factura_ref bigint;

create or replace view shg_dashboards.trazabilidad_nv as
with docs as (
    -- Una fila por línea de documento con NV resuelta. NCV viene con
    -- total_neto positivo en el Ventas Full (solo CANTIDAD y RESULTADO_*
    -- cambian de signo), por eso se resta más abajo.
    select
        v.nota_venta::bigint                                              as nota_venta,
        v.docto,
        v.num_docto,
        v.fecha_emision,
        v.cliente,
        trim(coalesce(v.nom_vddor, '') || ' ' || coalesce(v.apell_vddor, '')) as vendedor,
        coalesce(v.total_neto, 0)::double precision                       as total_neto
    from shg_dashboards.ventas_full v
    where v.nota_venta is not null
),
por_nv as (
    select
        nota_venta,
        sum(total_neto) filter (where docto in ('FAV', 'BOV', 'NDV'))              as facturado_bruto,
        sum(total_neto) filter (where docto = 'NCV')                               as notas_credito,
        count(distinct num_docto) filter (where docto in ('FAV', 'BOV', 'NDV'))    as n_facturas,
        string_agg(distinct num_docto::text, ', ') filter (where docto in ('FAV', 'BOV', 'NDV')) as facturas_lista,
        string_agg(distinct num_docto::text, ', ') filter (where docto = 'NCV')   as nc_lista
    from docs
    group by nota_venta
),
info_nv as (
    -- Cliente y vendedor según el primer documento emitido para la NV
    select distinct on (nota_venta) nota_venta, cliente, vendedor
    from docs
    order by nota_venta, fecha_emision, num_docto
),
guias_por_nv as (
    -- Solo informativo (N° guías); los montos ya no salen de aquí
    select nota_de_venta, count(distinct guia_despacho) as n_guias
    from shg_dashboards.guias
    where nota_de_venta is not null
    group by nota_de_venta
)
select
    nv.numnota,
    nv.fecha                                                           as fecha_nv,
    i.cliente                                                          as razon_social,
    i.vendedor,
    nv.totneto                                                         as valor_nv,
    coalesce(p.facturado_bruto, 0)::double precision                   as despachado_bruto,
    round(coalesce(p.notas_credito, 0))::bigint                        as notas_credito,
    (coalesce(p.facturado_bruto, 0) - coalesce(p.notas_credito, 0))::double precision as despachado_neto,
    (coalesce(p.facturado_bruto, 0) - coalesce(p.notas_credito, 0) - nv.totneto)::double precision as diferencia,
    -- Se redondea a pesos: el total de la NV viene entero y el Ventas Full con decimales
    round((coalesce(p.facturado_bruto, 0) - coalesce(p.notas_credito, 0))::numeric) > (nv.totneto + 1) as excede_valor_nv,
    p.n_facturas,
    coalesce(g.n_guias, 0)                                             as n_guias,
    p.facturas_lista,
    round(coalesce(p.notas_credito, 0) * 1.19)::bigint                 as notas_credito_iva,
    p.nc_lista
from shg_dashboards.notas_de_venta nv
join por_nv p        on p.nota_venta = nv.numnota
left join info_nv i  on i.nota_venta = nv.numnota
left join guias_por_nv g on g.nota_de_venta = nv.numnota;
