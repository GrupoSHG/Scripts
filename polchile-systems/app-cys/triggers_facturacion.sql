-- ============================================================
-- Recalculo automático de facturación (mano_obra + gastos_netos)
-- Se dispara cada vez que cambia 'asistencia' o 'gastos'
-- ============================================================

create or replace function fn_recalcular_facturacion(p_centro_costo_id uuid, p_mes date)
returns void as $$
declare
  v_mano_obra numeric;
  v_gastos numeric;
  v_inicio date := date_trunc('month', p_mes)::date;
  v_fin date := (date_trunc('month', p_mes) + interval '1 month' - interval '1 day')::date;
begin
  select coalesce(sum(p.tarifa_diaria), 0) into v_mano_obra
  from asistencia a
  join personas p on p.id = a.persona_id
  where a.centro_costo_id = p_centro_costo_id
    and a.presente = true
    and a.fecha between v_inicio and v_fin;

  select coalesce(sum(g.monto), 0) into v_gastos
  from gastos g
  where g.centro_costo_id = p_centro_costo_id
    and g.fecha between v_inicio and v_fin;

  insert into facturacion (centro_costo_id, mes, mano_obra, gastos_netos)
  values (p_centro_costo_id, v_inicio, v_mano_obra, v_gastos)
  on conflict (centro_costo_id, mes)
  do update set mano_obra = excluded.mano_obra, gastos_netos = excluded.gastos_netos;
end;
$$ language plpgsql;

-- Trigger sobre asistencia
create or replace function fn_trigger_asistencia_facturacion()
returns trigger as $$
begin
  perform fn_recalcular_facturacion(
    coalesce(new.centro_costo_id, old.centro_costo_id),
    coalesce(new.fecha, old.fecha)
  );
  return null;
end;
$$ language plpgsql;

drop trigger if exists trg_asistencia_facturacion on asistencia;
create trigger trg_asistencia_facturacion
after insert or update or delete on asistencia
for each row execute function fn_trigger_asistencia_facturacion();

-- Trigger sobre gastos
create or replace function fn_trigger_gastos_facturacion()
returns trigger as $$
begin
  perform fn_recalcular_facturacion(
    coalesce(new.centro_costo_id, old.centro_costo_id),
    coalesce(new.fecha, old.fecha)
  );
  return null;
end;
$$ language plpgsql;

drop trigger if exists trg_gastos_facturacion on gastos;
create trigger trg_gastos_facturacion
after insert or update or delete on gastos
for each row execute function fn_trigger_gastos_facturacion();
