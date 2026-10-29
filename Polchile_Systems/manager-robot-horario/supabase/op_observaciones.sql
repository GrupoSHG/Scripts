-- ============================================================================
-- Observaciones de las OP que no se pierden con la carga horaria del robot
-- ============================================================================
-- Las observaciones de la OP (NOTAOBS en Manager) traen las medidas a fabricar
-- de las bandejas ("46 x 7.500mm") que leen la bandejera y la PC4 (prensa.html)
-- y el plan de prensas. El informe de OP que descarga el robot cada hora NO
-- trae esa columna; la carga el pipeline diario (06:30,
-- manager-pipeline-diario/ConsultasSQL/Ordenes_de_produccion.sql). Antes, el
-- primer reemplazo del robot (09:07) dejaba todas las observaciones vacías.
--
-- Ahora reemplazar_ordenes_de_produccion:
--  1. guarda en op_observaciones las observaciones que tenga la tabla antes de
--     vaciarla (las del pipeline) y las que traiga la carga nueva;
--  2. reemplaza la tabla como antes;
--  3. rellena las observaciones vacías desde op_observaciones.
-- Una OP creada durante el día tiene sus observaciones desde el pipeline del
-- día siguiente, salvo que se agregue la columna al informe de Manager (el
-- robot ya la acepta: cargar.py, OPCIONALES).
--
-- Se aplica a mano (SQL Editor o supabase db query --linked -f). Idempotente.
-- ============================================================================
begin;

create table if not exists shg_dashboards.op_observaciones (
  num_op         bigint primary key,
  observaciones  text        not null,
  actualizado_en timestamptz not null default now()
);
comment on table shg_dashboards.op_observaciones is
  'Últimas observaciones conocidas de cada OP (NOTAOBS de Manager); reemplazar_ordenes_de_produccion las conserva entre cargas.';
alter table shg_dashboards.op_observaciones enable row level security;
revoke all on shg_dashboards.op_observaciones from anon, authenticated;
grant all on shg_dashboards.op_observaciones to service_role;

create or replace function shg_dashboards.reemplazar_ordenes_de_produccion(filas jsonb)
returns integer
language plpgsql
set search_path to 'shg_dashboards'
as $function$
declare n integer;
begin
  if jsonb_array_length(filas) = 0 then raise exception 'Sin filas: no se reemplaza ordenes_de_produccion'; end if;

  -- 1. Observaciones que ya están en la tabla (pipeline diario) y las que trae esta carga.
  insert into shg_dashboards.op_observaciones as oo (num_op, observaciones)
  select distinct on (num_op) num_op, observaciones
    from (select num_op, observaciones from shg_dashboards.ordenes_de_produccion
          union all
          select (f ->> 'num_op')::numeric::bigint, f ->> 'observaciones'
            from jsonb_array_elements(filas) f) x
   where num_op is not null and nullif(trim(observaciones), '') is not null
   order by num_op
  on conflict (num_op) do update
     set observaciones = excluded.observaciones, actualizado_en = now()
   where oo.observaciones is distinct from excluded.observaciones;

  -- 2. Reemplazo.
  delete from shg_dashboards.ordenes_de_produccion where true;
  insert into shg_dashboards.ordenes_de_produccion select * from jsonb_populate_recordset(null::shg_dashboards.ordenes_de_produccion, filas);
  get diagnostics n = row_count;

  -- 3. Observaciones que la carga no trae.
  update shg_dashboards.ordenes_de_produccion o
     set observaciones = oo.observaciones
    from shg_dashboards.op_observaciones oo
   where oo.num_op = o.num_op and nullif(trim(o.observaciones), '') is null;

  insert into shg_dashboards.cargas_manager (tabla, filas) values ('ordenes_de_produccion', n);
  return n;
end $function$;

commit;

select count(*) filter (where nullif(trim(observaciones), '') is not null) con_observaciones, count(*) total
  from shg_dashboards.ordenes_de_produccion;
