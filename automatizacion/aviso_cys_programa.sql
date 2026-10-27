-- ============================================================================
-- Avisos por correo de la App CyS (aviso-cys.yml) en la función VIVA
-- automatizacion.programa(): cada minuto, pero solo dispara el workflow si hay avisos
-- pendientes en app_cys.avisos_correo (app_cys.despachar_avisos_correo() los marca como
-- despachados y los vuelve a ofrecer a los 10 minutos si el correo no salió).
--
-- Requiere antes GrupoSHG_Systems/CyS_Systems/app-cys/avisos_correo.sql.
-- Lee la función tal como está en la base, inserta el bloque antes del "end" final si
-- no está y la recrea con los mismos atributos. Idempotente. Se aplica a mano.
-- El mismo bloque está en disparador_workflows.sql para que el archivo no se atrase.
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
  if to_regprocedure('app_cys.despachar_avisos_correo()') is null then
    raise exception 'Falta app_cys.despachar_avisos_correo(): aplica antes avisos_correo.sql';
  end if;
  if position('aviso-cys.yml' in src) > 0 then
    raise notice 'programa() ya dispara aviso-cys.yml: sin cambios';
    return;
  end if;

  nuevo := regexp_replace(src, 'end\s*;?\s*$',
    E'  -- App CyS: correo a supervisores/admin cuando un documento cambia de estado (si hay avisos)\n'
    || E'  if app_cys.despachar_avisos_correo() then\n'
    || E'    perform automatizacion.disparar(''aviso-cys.yml'');\n'
    || E'  end if;\n'
    || 'end');
  if nuevo = src then
    raise exception 'No se encontró el "end" final de programa()';
  end if;
  execute format(
    'create or replace function automatizacion.programa() returns void '
    || 'language plpgsql security definer set search_path = automatizacion, public as %L', nuevo);
  raise notice 'programa() actualizada: aviso-cys.yml cuando hay avisos pendientes';
end
$do$;

-- Comprobación:
-- select position('aviso-cys.yml' in prosrc) > 0 from pg_proc where proname = 'programa';
-- select * from automatizacion.ultimos_disparos where workflow = 'aviso-cys.yml' limit 5;
