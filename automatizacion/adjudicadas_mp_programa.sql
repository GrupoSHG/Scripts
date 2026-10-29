-- ============================================================================
-- Obras adjudicadas de Mercado Público para Polchile (adjudicadas-mp-polchile.yml) en la
-- función VIVA automatizacion.programa(): todos los días a las 23:20, sin reescribir el
-- resto de su cadencia. 23:20 cae dentro de la ventana de descargas masivas de ChileCompra
-- (22:00-07:00) y después del job de licitaciones de M5 (22:30), que usa el mismo ticket.
--
-- Lee la función tal como está en la base y, si no dispara adjudicadas-mp-polchile.yml,
-- inserta el bloque antes del "end" final. La recrea con los mismos atributos (security
-- definer, search_path). Idempotente. Se aplica a mano (SQL Editor o supabase db query),
-- después de Polchile_Systems/adjudicadas_mp.sql. El mismo bloque está en
-- disparador_workflows.sql para que el archivo no se atrase.
-- ============================================================================
do $do$
declare
  src text;
  nuevo text;
begin
  select prosrc into src from pg_proc
   where proname = 'programa' and pronamespace = 'automatizacion'::regnamespace;
  if src is null then
    raise exception 'No existe automatizacion.programa()';
  end if;

  if position('adjudicadas-mp-polchile.yml' in src) > 0 then
    raise notice 'programa() ya dispara adjudicadas-mp-polchile.yml: sin cambios';
    return;
  end if;
  nuevo := regexp_replace(src, 'end\s*;?\s*$',
    E'  -- Obras adjudicadas de Mercado Público (oportunidades Polchile): todos los días 23:20,\n'
    || E'  -- en la ventana de cargas masivas y después de licitaciones.yml (mismo ticket)\n'
    || E'  if h = 23 and mi = 20 then\n'
    || E'    perform automatizacion.disparar(''adjudicadas-mp-polchile.yml'');\n'
    || E'  end if;\n'
    || 'end');
  execute format(
    'create or replace function automatizacion.programa() returns void '
    || 'language plpgsql security definer set search_path = automatizacion, public as %L', nuevo);
  raise notice 'programa() actualizada: adjudicadas-mp-polchile.yml todos los días 23:20';
end
$do$;

-- Comprobación:
-- select position('adjudicadas-mp-polchile.yml' in prosrc) > 0 as programado from pg_proc where proname = 'programa';
-- select * from automatizacion.ultimos_disparos where workflow = 'adjudicadas-mp-polchile.yml' limit 5;
