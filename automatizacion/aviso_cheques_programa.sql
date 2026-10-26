-- ============================================================================
-- Aviso de cheques por cobrar (aviso-cheques.yml) en la función VIVA
-- automatizacion.programa(): todos los días a las 08:05, sin reescribir el resto
-- de su cadencia.
--
-- Lee la función tal como está en la base y:
--   * si no dispara aviso-cheques.yml, inserta el bloque antes del "end" final;
--   * si lo dispara solo en días hábiles (versión del 26/10/2026, Scripts#39),
--     le quita la condición "habil" para que corra también sábado y domingo
--     (un cheque fechado en fin de semana tiene su aviso el día anterior y el mismo día).
-- La recrea con los mismos atributos (security definer, search_path). Idempotente.
-- Se aplica a mano (SQL Editor o supabase db query). El mismo bloque está en
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

  if position('aviso-cheques.yml' in src) = 0 then
    nuevo := regexp_replace(src, 'end\s*;?\s*$',
      E'  -- Cheques por cobrar: correo a Finanzas si hay cobros hoy o mañana (todos los días)\n'
      || E'  if h = 8 and mi = 5 then\n'
      || E'    perform automatizacion.disparar(''aviso-cheques.yml'');\n'
      || E'  end if;\n'
      || 'end');
  else
    nuevo := replace(src,
      E'-- Cheques por cobrar: correo a Finanzas si hay cobros hoy o el próximo día hábil\n  if habil and h = 8 and mi = 5 then',
      E'-- Cheques por cobrar: correo a Finanzas si hay cobros hoy o mañana (todos los días)\n  if h = 8 and mi = 5 then');
  end if;

  if nuevo = src then
    raise notice 'programa() ya dispara aviso-cheques.yml todos los días: sin cambios';
    return;
  end if;
  execute format(
    'create or replace function automatizacion.programa() returns void '
    || 'language plpgsql security definer set search_path = automatizacion, public as %L', nuevo);
  raise notice 'programa() actualizada: aviso-cheques.yml todos los días 08:05';
end
$do$;

-- Comprobación:
-- select position('if h = 8 and mi = 5 then' in prosrc) > 0 as todos_los_dias from pg_proc where proname = 'programa';
-- select * from automatizacion.ultimos_disparos where workflow = 'aviso-cheques.yml' limit 5;
