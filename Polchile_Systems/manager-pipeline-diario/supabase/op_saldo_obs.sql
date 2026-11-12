-- ============================================================================
-- op_saldo_obs.sql — saldo real de cada OP abierta según sus observaciones
-- ============================================================================
-- Las observaciones de las OP en Manager anotan lo fabricado con fecha
-- ("26/08/26 / 05 x 12.570 = 62.85m2 P-1", "31/08/26 / 35 x 5.670"). En las
-- OP de bandeja (PSA) además traen el pedido sin fecha ("43 x 12.070mm / 35 x
-- 5.670mm"). Manager no siempre descuenta lo anotado en cantidad_terminada,
-- así que el WIP (wip_bandejas, compras_diarias.sql) usa este saldo:
--   * con pedido en las observaciones y todos los largos anotados dentro del
--     pedido: Σ (pedido − anotado) por largo;
--   * sin pedido en las observaciones (paneles: el pedido está en la NV):
--     cantidad_op − anotado;
--   * en la unidad de la OP (m² en paneles: × ancho 1 / 1,15 / 0,91; ml en
--     bandejas). Si Manager informa un saldo menor, manda Manager.
-- Misma lectura que plan.html / prensa.html (porFabricar) y 05_plan.js
-- (hechosDeObservaciones_). 03/11/2026. Va ANTES de compras_diarias.sql (la
-- vista wip_bandejas la usa). Se aplica a mano; es idempotente.
-- 06/11/2026: si la OP tiene lo que queda por fabricar cargado a mano
-- (shg_dashboards.op_medidas_manual, GrupoSHG_Systems
-- Polchile_Systems/dashboard-produccion/op_medidas_manual.sql, aplicar ANTES),
-- esa lista reemplaza las observaciones y manda sobre Manager
-- (medidas_manual = true).
-- 12/11/2026: también se descuenta lo que la planta registró en las tablets
-- (shg_dashboards.avance_prensas, en la unidad de la OP), con la misma regla
-- del plan de prensas: saldo = mínimo entre lo anterior y cantidad de la OP −
-- todo lo registrado; con medidas a mano, la lista − lo registrado desde que
-- se cargó. Así una OP terminada en planta sale del WIP de bandejas aunque
-- Manager todavía la muestre abierta (avance_planta = lo registrado).
-- ============================================================================
begin;

-- Pedido (líneas sin fecha, "NN x N.NNNmm") y anotado como fabricado (líneas
-- con fecha, "NN x N.NNN" o "NN x 2.71" en metros), por largo en mm.
create or replace function shg_dashboards.obs_por_largo(texto text)
returns table (largo_mm int, pedido int, hecho int)
language sql immutable
as $$
  with lineas as (
    select trim(l) as l from regexp_split_to_table(coalesce(texto, ''), '\r?\n') as l
  ),
  ped as (
    select (m)[1]::int as p, replace(replace((m)[2], '.', ''), ',', '')::int as mm
      from lineas, lateral regexp_matches(l, '(\d+)\s*[xX×]\s*(\d{1,3}(?:[.,]\d{3})+|\d+)\s*mm', 'g') as m
     where l !~ '^\d{1,2}/\d{1,2}/\d{2,4}'
  ),
  hec as (
    select (m)[1]::int as p,
           case when (m)[2] ~ '[.,]\d{3}$' then replace(replace((m)[2], '.', ''), ',', '')::int
                when replace((m)[2], ',', '.')::numeric < 100 then round(replace((m)[2], ',', '.')::numeric * 1000)::int
                else round(replace((m)[2], ',', '.')::numeric)::int end as mm
      from lineas,
           lateral regexp_matches(split_part(regexp_replace(l, '^\d{1,2}/\d{1,2}/\d{2,4}', ''), '=', 1),
                                  '(\d+)\s*[xX×]\s*(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)', 'g') as m
     where l ~ '^\d{1,2}/\d{1,2}/\d{2,4}'
  )
  select coalesce(a.mm, b.mm), coalesce(a.p, 0), coalesce(b.p, 0)
    from (select mm, sum(p)::int as p from ped where p > 0 and mm > 0 group by mm) a
    full join (select mm, sum(p)::int as p from hec where p > 0 and mm > 0 group by mm) b on a.mm = b.mm;
$$;

create or replace view shg_dashboards.op_saldo_obs
with (security_invoker = on) as
with op as (
  select distinct on (o.num_op) o.num_op, o.nota_vta, o.codigo_producto, o.nombre_producto, o.unidmed,
         o.cantidad_op::numeric as cantidad_op, o.cantidad_pendiente::numeric as pend_manager,
         coalesce(mm.medidas, o.observaciones) as observaciones,
         mm.num_op is not null as manual,
         mm.creado_en as manual_desde,
         case when o.unidmed = 'M2' then (case when o.nombre_producto ~ 'a1150' then 1.15
                                               when o.nombre_producto ~ 'a910' then 0.91 else 1.0 end)
              else 1.0 end as ancho
    from shg_dashboards.ordenes_de_produccion o
    left join shg_dashboards.op_medidas_manual mm on mm.num_op = o.num_op
   where o.cantidad_pendiente > 0 and o.unidmed in ('M2', 'Ml')
   order by o.num_op
),
lect as (
  select o.num_op,
         coalesce(sum(x.pedido * x.largo_mm), 0) / 1000.0                                    as pedido_ml,
         coalesce(sum(x.hecho * x.largo_mm), 0) / 1000.0                                     as hecho_ml,
         coalesce(sum(greatest(x.pedido - x.hecho, 0) * x.largo_mm), 0) / 1000.0             as resto_ml,
         coalesce(bool_or(x.hecho > 0 and x.pedido = 0), false)                              as ajenos
    from op o
    left join lateral shg_dashboards.obs_por_largo(o.observaciones) x on true
   group by o.num_op
),
av as (
  select o.num_op,
         coalesce(sum(case when o.unidmed = 'Ml' then a.ml else a.m2 end), 0)::numeric as total,
         coalesce(sum(case when o.unidmed = 'Ml' then a.ml else a.m2 end)
                    filter (where o.manual and a.registrado_en > o.manual_desde), 0)::numeric as desde_manual
    from op o
    left join shg_dashboards.avance_prensas a on a.num_op = o.num_op
   group by o.num_op
)
select o.num_op, o.nota_vta, o.codigo_producto, o.nombre_producto, o.unidmed,
       o.cantidad_op, o.pend_manager,
       round((l.hecho_ml * o.ancho)::numeric, 2) as anotado,
       l.ajenos and l.pedido_ml > 0 as largos_ajenos,
       case
         when o.manual then round((l.resto_ml * o.ancho)::numeric, 2)
         when l.hecho_ml = 0 then null
         when l.pedido_ml > 0 and not l.ajenos then round((l.resto_ml * o.ancho)::numeric, 2)
         when l.pedido_ml = 0 then round(greatest(0, o.cantidad_op - l.hecho_ml * o.ancho)::numeric, 2)
       end as saldo_obs,
       case when o.manual then round(greatest(0, l.resto_ml * o.ancho - v.desde_manual)::numeric, 2)
       else round(least(o.pend_manager, greatest(0, o.cantidad_op - v.total), coalesce(
         case
           when l.hecho_ml = 0 then null
           when l.pedido_ml > 0 and not l.ajenos then l.resto_ml * o.ancho
           when l.pedido_ml = 0 then greatest(0, o.cantidad_op - l.hecho_ml * o.ancho)
         end, o.pend_manager))::numeric, 2) end as saldo,
       o.manual as medidas_manual,
       round(v.total, 2) as avance_planta
  from op o join lect l on l.num_op = o.num_op join av v on v.num_op = o.num_op;

comment on view shg_dashboards.op_saldo_obs is
  'Saldo de cada OP abierta: el menor entre Manager, pedido − lo anotado en sus observaciones y cantidad − lo registrado en planta (avance_prensas); si hay op_medidas_manual, esa lista − lo registrado desde la carga.';
revoke all on shg_dashboards.op_saldo_obs from anon;
grant select on shg_dashboards.op_saldo_obs to authenticated;
grant execute on function shg_dashboards.obs_por_largo(text) to authenticated, service_role;

commit;
