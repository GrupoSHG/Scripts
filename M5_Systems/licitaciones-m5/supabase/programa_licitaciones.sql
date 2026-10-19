-- Cambia el disparo de las 22:30 de automatizacion.programa() de mercado-publico-m5.yml a licitaciones.yml.
-- Se aplica UNA vez, después de fusionar el PR que agrega .github/workflows/licitaciones.yml a main
-- (antes de eso GitHub responde 404 al disparo). Toca solo esa línea de la función EN VIVO, que puede
-- diferir de automatizacion/disparador_workflows.sql (ver CLAUDE.md: no re-aplicar el archivo entero).
-- Idempotente: si ya dispara licitaciones.yml, no hace nada.
do $$
declare
  antes   text := pg_get_functiondef('automatizacion.programa'::regproc);
  despues text;
begin
  if position('''licitaciones.yml''' in antes) > 0 and position('mercado-publico-m5.yml' in antes) = 0 then
    raise notice 'programa() ya dispara licitaciones.yml: sin cambios';
    return;
  end if;
  -- perform automatizacion.disparar('mercado-publico-m5.yml' ...);  ->  perform automatizacion.disparar('licitaciones.yml');
  despues := regexp_replace(antes,
    'perform automatizacion\.disparar\(''mercado-publico-m5\.yml''[^;]*;',
    'perform automatizacion.disparar(''licitaciones.yml'');');
  if despues = antes or position('mercado-publico-m5.yml' in despues) > 0 then
    raise exception 'No se encontró exactamente el disparo de mercado-publico-m5.yml en programa(); revisar a mano.';
  end if;
  execute despues;
  raise notice 'programa(): 22:30 ahora dispara licitaciones.yml';
end $$;

select regexp_replace(substring(prosrc from position('22 and mi = 30' in prosrc) - 10 for 200), '\s+', ' ', 'g') as bloque_2230
from pg_proc where proname = 'programa';
