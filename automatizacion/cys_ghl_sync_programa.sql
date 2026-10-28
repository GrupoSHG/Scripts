-- ============================================================================
-- CRM CyS (cys-ghl-sync.yml) en la automatización, sobre las funciones VIVAS:
--   1. automatizacion.programa(): lo dispara a las 08:14, 12:14, 16:14 y 20:14 (Santiago),
--      dos minutos después del CRM de M5 (que corre a :12 en las mismas horas).
--   2. automatizacion.workflows_manual: fila para el botón "Actualizar datos".
--   3. automatizacion.ultimo_dato(): fecha del dato = max(sincronizado_en) de cys.oportunidades.
--
-- Requiere antes CyS_Systems/crm_cys.sql. Lee cada función tal como está en la base, inserta
-- el bloque si no está y la recrea con los mismos atributos. Idempotente. Se aplica a mano.
-- El mismo bloque está en disparador_workflows.sql y actualizar_datos_manual.sql para que
-- los archivos no se atrasen.
-- ============================================================================
do $do$
declare
  src text;
  nuevo text;
begin
  if to_regclass('cys.oportunidades') is null then
    raise exception 'Falta cys.oportunidades: aplica antes CyS_Systems/crm_cys.sql';
  end if;

  -- 1. programa()
  select prosrc into src from pg_proc
   where proname = 'programa' and pronamespace = 'automatizacion'::regnamespace;
  if src is null then
    raise exception 'No existe automatizacion.programa()';
  end if;
  if position('cys-ghl-sync.yml' in src) > 0 then
    raise notice 'programa() ya dispara cys-ghl-sync.yml: sin cambios';
  else
    nuevo := regexp_replace(src, 'end\s*;?\s*$',
      E'  -- CRM CyS (GoHighLevel), dos minutos después del de M5\n'
      || E'  if h in (8, 12, 16, 20) and mi = 14 then\n'
      || E'    perform automatizacion.disparar(''cys-ghl-sync.yml'');\n'
      || E'  end if;\n'
      || 'end');
    if nuevo = src then
      raise exception 'No se encontró el "end" final de programa()';
    end if;
    execute format(
      'create or replace function automatizacion.programa() returns void '
      || 'language plpgsql security definer set search_path = automatizacion, public as %L', nuevo);
    raise notice 'programa() actualizada: cys-ghl-sync.yml a las 8/12/16/20:14';
  end if;

  -- 3. ultimo_dato()
  select prosrc into src from pg_proc
   where proname = 'ultimo_dato' and pronamespace = 'automatizacion'::regnamespace;
  if position('cys-ghl-sync.yml' in src) > 0 then
    raise notice 'ultimo_dato() ya conoce cys-ghl-sync.yml: sin cambios';
  else
    nuevo := regexp_replace(src, '(\s*)end\s*;?\s*$',
      E'\n    when ''cys-ghl-sync.yml''      then (select max(sincronizado_en) from cys.oportunidades)\\1end;\n');
    if nuevo = src then
      raise exception 'No se encontró el "end" del case en ultimo_dato()';
    end if;
    execute format(
      'create or replace function automatizacion.ultimo_dato(p_workflow text) returns timestamptz '
      || 'language sql stable security definer set search_path = automatizacion, public as %L', nuevo);
    raise notice 'ultimo_dato() actualizada: cys-ghl-sync.yml';
  end if;
end
$do$;

-- 2. Botón "Actualizar datos"
insert into automatizacion.workflows_manual (workflow, nombre, inputs, espera_min, duracion_min)
values ('cys-ghl-sync.yml', 'CRM CyS (GoHighLevel)', '{}', 5, 2)
on conflict (workflow) do nothing;

-- Comprobación:
-- select position('cys-ghl-sync.yml' in prosrc) > 0 from pg_proc where proname in ('programa', 'ultimo_dato');
-- select automatizacion.ultimo_dato('cys-ghl-sync.yml');
-- select * from automatizacion.ultimos_disparos where workflow = 'cys-ghl-sync.yml' limit 5;
