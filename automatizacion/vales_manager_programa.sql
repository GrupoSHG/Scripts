-- vales_manager_programa.sql — agrega a automatizacion.programa() los horarios de
-- vales-manager.yml (12/11/2026), SIN reescribir el resto de la función: toma la
-- definición viva (pg_get_functiondef) e inserta el bloque antes del "end" final.
-- Si el bloque ya está, no hace nada. Idempotente.
--   modo hora: lun–sáb, 09:35 a 18:35, cada hora (después del robot de los :07).
--   modo dia:  lun y mar 18:00; mié–sáb 17:00 (producción del día sin subir a Manager).
do $do$
declare
  def   text;
  nuevo text;
begin
  select pg_get_functiondef('automatizacion.programa()'::regprocedure) into def;
  if def like '%vales-manager.yml%' then
    raise notice 'programa() ya dispara vales-manager.yml: no se cambia';
    return;
  end if;
  nuevo := regexp_replace(def, 'end\s*\$function\$\s*$', $b$  -- Vales de Manager con el avance de planta (Producción Polchile): cada hora lun–sáb y
  -- resumen de lo no importado (lun/mar 18:00, mié–sáb 17:00). Scripts: vales-manager.yml
  if extract(isodow from t) <= 6 and h between 9 and 18 and mi = 35 then
    perform automatizacion.disparar('vales-manager.yml', '{"modo": "hora"}');
  end if;
  if (extract(isodow from t) in (1, 2) and h = 18 and mi = 0)
     or (extract(isodow from t) between 3 and 6 and h = 17 and mi = 0) then
    perform automatizacion.disparar('vales-manager.yml', '{"modo": "dia"}');
  end if;
end
$function$
$b$);
  if nuevo = def then
    raise exception 'No se encontró el "end" final de programa(): revisar a mano';
  end if;
  execute nuevo;
  raise notice 'programa() actualizada con vales-manager.yml';
end
$do$;
