-- ============================================================================
-- Agrega el aviso de cheques por cobrar (aviso-cheques.yml, lun-vie 08:05) a la
-- función VIVA automatizacion.programa(), sin reescribir el resto de su cadencia.
--
-- Lee la función tal como está en la base, inserta el bloque antes del "end" final
-- y la recrea con los mismos atributos (security definer, search_path). Si el
-- bloque ya está, no hace nada. Se aplica a mano (SQL Editor o supabase db query).
-- El mismo bloque quedó en disparador_workflows.sql para que el archivo no se atrase.
-- ============================================================================
do $do$
declare
  src text;
begin
  select prosrc into src from pg_proc
   where proname = 'programa' and pronamespace = 'automatizacion'::regnamespace;
  if src is null then
    raise exception 'No existe automatizacion.programa()';
  end if;
  if position('aviso-cheques.yml' in src) > 0 then
    raise notice 'programa() ya dispara aviso-cheques.yml: sin cambios';
    return;
  end if;
  src := regexp_replace(src, 'end\s*;?\s*$',
    E'  -- Cheques por cobrar: correo a Finanzas si hay cobros hoy o el próximo día hábil\n'
    || E'  if habil and h = 8 and mi = 5 then\n'
    || E'    perform automatizacion.disparar(''aviso-cheques.yml'');\n'
    || E'  end if;\n'
    || 'end');
  execute format(
    'create or replace function automatizacion.programa() returns void '
    || 'language plpgsql security definer set search_path = automatizacion, public as %L', src);
  raise notice 'programa() actualizada: aviso-cheques.yml lun-vie 08:05';
end
$do$;

-- Comprobación:
-- select position('aviso-cheques.yml' in prosrc) > 0 as tiene_aviso from pg_proc where proname = 'programa';
-- select * from automatizacion.ultimos_disparos where workflow = 'aviso-cheques.yml' limit 5;
