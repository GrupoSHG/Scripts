-- ============================================================================
-- compras_diarias.sql — qué comprar hoy, qué NV pueden liberarse y WIP de bandejas
-- ============================================================================
-- Sale de la reunión de producción del 20/10/2026: la planificación parte de
-- la fecha de entrega y de tener los materiales. Cada día se desarma lo
-- pendiente (OP abiertas y NV sin OP) según las recetas de Manager, se compara
-- con el stock (planta + Los Paltos) y con las OC por llegar, y sale:
--   * compras_sugeridas: por material comprado, cuánto falta y cuánto comprar.
--   * nv_materiales:     por NV, si todo su material está en bodega (se puede
--                        liberar / generar la OP), espera una OC o falta comprar.
--   * wip_bandejas:      por bandeja PSA, cuánto piden las OP de paneles y las
--                        NV, cuánto hay en stock y en OP de bandejas, y cuánto
--                        falta programar (el WIP previo a las prensas).
--
-- Tablas de origen (las crea el pipeline diario, bulk_sync_supabase.py, desde
-- ConsultasSQL/Necesidades_Materiales.sql e Insumos_Disponibilidad.sql, con
-- RLS de lectura para authenticated): shg_dashboards.necesidades_materiales y
-- shg_dashboards.insumos_disponibilidad.
--
-- Aplicar UNA vez en el SQL Editor de Supabase después de la primera corrida
-- del pipeline que cree esas tablas. Si cambian las columnas de las consultas,
-- el cargador recrea las tablas: antes hay que borrar estas vistas (drop view)
-- y volver a correr este archivo.
--
-- Asignación del stock: primero las OP abiertas (ya comprometidas) y después
-- las NV sin OP; dentro de cada grupo, por fecha de entrega y número de NV.
-- No descuenta stock de bandejas ya fabricadas al desarmar las NV sin OP (la
-- cuenta de acero es conservadora); wip_bandejas sí las considera.
-- ============================================================================
begin;

-- Mismas guardas que el resto de las tablas de Manager (accesos/clientes_m5.sql
-- y crm_vendedores.sql en GrupoSHG_Systems): ni el portal de clientes M5 ni
-- los vendedores leen datos de producción. El cargador solo crea la política
-- de lectura lectura_publica_<tabla>; las vistas de abajo son security
-- invoker, así que heredan estas restricciones.
drop policy if exists sin_clientes_externos on shg_dashboards.necesidades_materiales;
create policy sin_clientes_externos on shg_dashboards.necesidades_materiales as restrictive
  for all to authenticated
  using ((select coalesce(shg_dashboards.rol_actual(), '')) <> 'cliente');
drop policy if exists vendedor_solo_lo_suyo on shg_dashboards.necesidades_materiales;
create policy vendedor_solo_lo_suyo on shg_dashboards.necesidades_materiales as restrictive
  for all to authenticated
  using (not (select shg_dashboards.es_vendedor()));
drop policy if exists sin_clientes_externos on shg_dashboards.insumos_disponibilidad;
create policy sin_clientes_externos on shg_dashboards.insumos_disponibilidad as restrictive
  for all to authenticated
  using ((select coalesce(shg_dashboards.rol_actual(), '')) <> 'cliente');
drop policy if exists vendedor_solo_lo_suyo on shg_dashboards.insumos_disponibilidad;
create policy vendedor_solo_lo_suyo on shg_dashboards.insumos_disponibilidad as restrictive
  for all to authenticated
  using (not (select shg_dashboards.es_vendedor()));

drop view if exists shg_dashboards.wip_bandejas;
drop view if exists shg_dashboards.nv_materiales;
drop view if exists shg_dashboards.compras_sugeridas;
drop view if exists shg_dashboards.necesidades_asignadas;

-- Cada fila de material comprado con su lugar en la fila de prioridad y la
-- cobertura que le toca: en_bodega, con_oc (lo cubre una OC por llegar) o
-- falta_comprar.
create view shg_dashboards.necesidades_asignadas
with (security_invoker = on) as
with req as (
  select
    n.origen,
    n.nota_vta,
    n.num_op,
    nullif(n.fecha_entrega, '')::date               as fecha_entrega,
    n.codigo_producto,
    n.nombre_producto,
    n.codigo_componente                             as codigo,
    n.nombre_componente                             as nombre,
    n.unidad_componente                             as unidad,
    sum(n.cantidad_requerida)::numeric              as cantidad
  from shg_dashboards.necesidades_materiales n
  where n.es_comprado = 1
  group by 1, 2, 3, 4, 5, 6, 7, 8, 9
),
acum as (
  select
    r.*,
    coalesce(d.stk_total, 0)::numeric               as stk_total,
    coalesce(d.por_llegar, 0)::numeric              as por_llegar,
    sum(r.cantidad) over (
      partition by r.codigo
      order by case r.origen when 'OP' then 0 else 1 end,
               r.fecha_entrega nulls last, r.nota_vta, r.num_op, r.codigo_producto
      rows between unbounded preceding and current row
    )                                               as acumulado
  from req r
  left join shg_dashboards.insumos_disponibilidad d on d.codigo = r.codigo
)
select
  a.*,
  case
    when a.acumulado <= greatest(a.stk_total, 0)                  then 'en_bodega'
    when a.acumulado <= greatest(a.stk_total, 0) + a.por_llegar   then 'con_oc'
    else 'falta_comprar'
  end as cobertura
from acum a;

-- Por material comprado: demanda, stock, OC por llegar y cuánto comprar.
create view shg_dashboards.compras_sugeridas
with (security_invoker = on) as
with dem as (
  select
    codigo,
    sum(cantidad) filter (where origen = 'OP')      as demanda_op,
    sum(cantidad) filter (where origen = 'NV')      as demanda_nv,
    sum(cantidad)                                   as demanda_total,
    count(distinct nota_vta)                        as notas_venta,
    min(fecha_entrega) filter (where cobertura <> 'en_bodega') as primera_fecha_sin_stock
  from shg_dashboards.necesidades_asignadas
  group by codigo
)
select
  d.codigo,
  d.nombre,
  d.unidad,
  d.familia,
  coalesce(m.demanda_op, 0)                         as demanda_op,
  coalesce(m.demanda_nv, 0)                         as demanda_nv,
  coalesce(m.demanda_total, 0)                      as demanda_total,
  coalesce(m.notas_venta, 0)                        as notas_venta,
  d.stk_planta,
  d.stk_los_paltos,
  d.stk_total,
  d.por_llegar,
  d.oc_pendientes,
  nullif(d.proxima_llegada, '')::date               as proxima_llegada,
  (nullif(d.proxima_llegada, '')::date < current_date) as oc_atrasada,
  d.oc_detalle,
  greatest(coalesce(m.demanda_total, 0) - greatest(d.stk_total, 0), 0)                as falta_en_bodega,
  greatest(coalesce(m.demanda_total, 0) - greatest(d.stk_total, 0) - d.por_llegar, 0) as comprar,
  round((greatest(coalesce(m.demanda_total, 0) - greatest(d.stk_total, 0) - d.por_llegar, 0)
         * d.precio_ultima_compra)::numeric, 0)     as costo_estimado,
  d.precio_ultima_compra,
  m.primera_fecha_sin_stock
from shg_dashboards.insumos_disponibilidad d
join dem m on m.codigo = d.codigo
where d.es_comprado = 1;

-- Por NV (y OP): estado de materiales. "Lista" = todo en bodega.
create view shg_dashboards.nv_materiales
with (security_invoker = on) as
select
  origen,
  nota_vta,
  num_op,
  min(fecha_entrega)                                as fecha_entrega,
  string_agg(distinct codigo_producto, ', ')        as productos,
  count(distinct codigo)                            as materiales,
  count(distinct codigo) filter (where cobertura = 'en_bodega')     as en_bodega,
  count(distinct codigo) filter (where cobertura = 'con_oc')        as con_oc,
  count(distinct codigo) filter (where cobertura = 'falta_comprar') as falta_comprar,
  case
    when bool_or(cobertura = 'falta_comprar') then 'Falta comprar'
    when bool_or(cobertura = 'con_oc')        then 'Espera OC'
    else 'Lista'
  end                                               as estado,
  string_agg(distinct codigo || ' (' || nombre || ')', '; ')
    filter (where cobertura <> 'en_bodega')         as materiales_pendientes
from shg_dashboards.necesidades_asignadas
group by origen, nota_vta, num_op;

-- WIP de bandejas (PSA): lo que piden las OP de paneles y las NV sin OP,
-- más las bandejas vendidas directo, contra el stock de bandejas y lo que ya
-- está en OP de bandejas.
create view shg_dashboards.wip_bandejas
with (security_invoker = on) as
with productos as (
  -- Saldo de cada OP / NV sin OP una sola vez (necesidades_materiales repite
  -- el producto en cada fila de componente)
  select distinct origen, nota_vta, num_op, fecha_entrega,
         codigo_producto, nombre_producto, unidad_producto, cantidad_producto
  from shg_dashboards.necesidades_materiales
  where codigo_producto like 'PSA%'
),
-- Por bandeja y NV: lo que piden sus paneles (OP o NV sin OP), lo que se vende
-- directo sin OP y lo que ya está en OP de bandejas de esa misma NV. Una OP de
-- bandeja cubre primero los paneles de su NV; si la NV no tiene paneles que la
-- pidan, es venta directa y su saldo es la necesidad.
por_nv as (
  select
    codigo,
    nota_vta,
    max(nombre)                                     as nombre,
    max(unidad)                                     as unidad,
    coalesce(sum(cantidad) filter (where tipo = 'panel_op'), 0) as para_op_paneles,
    coalesce(sum(cantidad) filter (where tipo = 'panel_nv'), 0) as para_nv_paneles,
    coalesce(sum(cantidad) filter (where tipo = 'directa_nv'), 0) as venta_directa_sin_op,
    coalesce(sum(cantidad) filter (where tipo = 'en_op'), 0)    as en_op,
    string_agg(num_op::text, ', ') filter (where tipo = 'en_op') as ops,
    min(fecha_entrega)                              as primera_entrega
  from (
    select case origen when 'OP' then 'panel_op' else 'panel_nv' end as tipo,
           codigo_componente as codigo, nota_vta, num_op,
           nombre_componente as nombre, unidad_componente as unidad,
           cantidad_requerida as cantidad, nullif(fecha_entrega, '')::date as fecha_entrega
    from shg_dashboards.necesidades_materiales
    where codigo_componente like 'PSA%'
    union all
    select case origen when 'OP' then 'en_op' else 'directa_nv' end,
           codigo_producto, nota_vta, num_op, nombre_producto, unidad_producto,
           cantidad_producto, nullif(fecha_entrega, '')::date
    from productos
  ) t
  group by codigo, nota_vta
),
pedido as (
  select
    codigo,
    max(nombre)                                     as nombre,
    max(unidad)                                     as unidad,
    sum(para_op_paneles)                            as para_op_paneles,
    sum(para_nv_paneles)                            as para_nv_paneles,
    sum(venta_directa_sin_op
        + greatest(en_op - para_op_paneles - para_nv_paneles, 0)) as venta_directa,
    sum(greatest(para_op_paneles + para_nv_paneles, en_op) + venta_directa_sin_op) as requerido,
    sum(en_op)                                      as en_op,
    -- lo que falta poner en OP de bandejas, NV por NV, antes de mirar el stock
    sum(greatest(para_op_paneles + para_nv_paneles - en_op, 0) + venta_directa_sin_op) as sin_op,
    string_agg(ops, ', ')                           as ops,
    min(primera_entrega)                            as primera_entrega,
    string_agg(nota_vta::text, ', ' order by primera_entrega, nota_vta)
      filter (where greatest(para_op_paneles + para_nv_paneles - en_op, 0)
                    + venta_directa_sin_op > 0)     as notas_venta_sin_op
  from por_nv
  group by codigo
)
select
  p.codigo,
  coalesce(p.nombre, d.nombre)                      as nombre,
  coalesce(p.unidad, d.unidad)                      as unidad,
  p.para_op_paneles,
  p.para_nv_paneles,
  p.venta_directa,
  p.requerido,
  greatest(coalesce(d.stk_total, 0), 0)             as stock,
  p.en_op,
  p.ops,
  greatest(p.sin_op - greatest(coalesce(d.stk_total, 0), 0), 0) as falta_programar,
  p.primera_entrega,
  p.notas_venta_sin_op
from pedido p
left join shg_dashboards.insumos_disponibilidad d on d.codigo = p.codigo;

revoke all on shg_dashboards.necesidades_asignadas, shg_dashboards.compras_sugeridas,
              shg_dashboards.nv_materiales, shg_dashboards.wip_bandejas from anon;
grant select on shg_dashboards.necesidades_asignadas, shg_dashboards.compras_sugeridas,
                shg_dashboards.nv_materiales, shg_dashboards.wip_bandejas to authenticated;

commit;

-- Revisión rápida
select familia, count(*) materiales, count(*) filter (where comprar > 0) a_comprar,
       sum(costo_estimado) costo_estimado
from shg_dashboards.compras_sugeridas group by 1 order by 1;
select origen, estado, count(*) from shg_dashboards.nv_materiales group by 1, 2 order by 1, 2;
