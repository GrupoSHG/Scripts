-- ============================================================================
-- Botón "Actualizar datos" de los dashboards: disparo manual de un workflow
-- ============================================================================
-- Complementa disparador_workflows.sql (requiere que ya exista el schema
-- automatizacion y el secret github_token en Vault). Los dashboards llaman, con
-- la sesión de admin-session.js (rol authenticated), a dos RPC del schema public:
--
--   actualizar_datos(p_workflow)     pide a GitHub correr el workflow ahora y
--                                    devuelve el estado. Si ya se pidió hace poco
--                                    (espera_min) no vuelve a disparar.
--   estado_actualizacion(p_workflow) última carga de datos, último disparo y si
--                                    hay una actualización en curso. El botón
--                                    la consulta cada 20 s hasta ver datos nuevos.
--
-- Solo se pueden disparar los workflows anotados en automatizacion.workflows_manual.
-- Quién lo pidió queda en automatizacion.disparos.solicitado_por (NULL = pg_cron).
-- Revisar:  select * from automatizacion.ultimos_disparos limit 20;
-- Correr en el SQL Editor del proyecto ffxopvzxyeacpbtxuagu (ya aplicado el 02/10/2026).
-- ============================================================================

alter table automatizacion.disparos add column if not exists solicitado_por text;

create table if not exists automatizacion.workflows_manual (
  workflow     text primary key,              -- archivo en .github/workflows
  nombre       text not null,                 -- cómo se describe en el botón
  inputs       jsonb not null default '{}'::jsonb,
  espera_min   int  not null default 10,      -- no volver a disparar antes de esto
  duracion_min int  not null default 8        -- cuánto suele demorar (mensaje y tope del sondeo)
);

insert into automatizacion.workflows_manual (workflow, nombre, inputs, espera_min, duracion_min) values
  ('manager-descargas.yml', 'Descargas de Manager (NV, ventas, OP, CxC)', '{"forzar": "true", "sin_cargar": "false"}', 10, 8),
  ('ghl-polchile-sync.yml', 'CRM Polchile (GoHighLevel)',                '{}', 5, 3),
  ('m5-ghl-sync.yml',       'CRM M5 Industrial (GoHighLevel)',           '{}', 5, 2),
  ('pipeline.yml',          'Pipeline Manager (NV pendientes, stock, facturación)', '{}', 30, 15)
on conflict (workflow) do update set nombre = excluded.nombre, inputs = excluded.inputs,
  espera_min = excluded.espera_min, duracion_min = excluded.duracion_min;

-- disparar() ahora registra quién lo pidió. Se reemplaza la firma (text, jsonb) para
-- que las llamadas con 1 o 2 argumentos no queden ambiguas.
drop function if exists automatizacion.disparar(text, jsonb);
create or replace function automatizacion.disparar(p_workflow text, p_inputs jsonb default '{}'::jsonb, p_solicitado_por text default null)
returns void language plpgsql security definer set search_path = automatizacion, extensions, public as $$
declare
  v_token text;
  v_req bigint;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'github_token' limit 1;
  if v_token is null then
    insert into automatizacion.disparos (workflow, detalle, solicitado_por)
    values (p_workflow, 'sin token: falta el secret github_token en Vault', p_solicitado_por);
    return;
  end if;
  select net.http_post(
    url := 'https://api.github.com/repos/GrupoSHG/Scripts/actions/workflows/' || p_workflow || '/dispatches',
    body := jsonb_build_object('ref', 'main', 'inputs', p_inputs),
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || v_token,
      'Accept', 'application/vnd.github+json',
      'X-GitHub-Api-Version', '2022-11-28',
      'User-Agent', 'polchile-supabase-cron'),
    timeout_milliseconds := 10000
  ) into v_req;
  insert into automatizacion.disparos (workflow, request_id, solicitado_por) values (p_workflow, v_req, p_solicitado_por);
end $$;
revoke all on function automatizacion.disparar(text, jsonb, text) from public, anon, authenticated;

-- Fecha/hora de los datos que cada workflow deja en Supabase.
create or replace function automatizacion.ultimo_dato(p_workflow text)
returns timestamptz language sql stable security definer set search_path = automatizacion, public as $$
  select case p_workflow
    when 'manager-descargas.yml' then shg_dashboards.ultima_carga_manager()
    when 'ghl-polchile-sync.yml' then (select max(sincronizado_en) from polchile_crm.oportunidades)
    when 'm5-ghl-sync.yml'       then (select max(sincronizado_en) from m5.oportunidades)
    when 'pipeline.yml'          then greatest(
                                        (select max(actualizado_en) from shg_dashboards.notas_venta_pendientes),
                                        (select max(actualizado_en) from shg_dashboards.facturacion_periodo))
  end;
$$;
revoke all on function automatizacion.ultimo_dato(text) from public, anon, authenticated;

create or replace function public.estado_actualizacion(p_workflow text)
returns jsonb language plpgsql stable security definer set search_path = automatizacion, public as $$
declare
  w automatizacion.workflows_manual%rowtype;
  d record;
  v_dato timestamptz;
  v_aceptado boolean;
begin
  select * into w from automatizacion.workflows_manual where workflow = p_workflow;
  if not found then raise exception 'Workflow no habilitado para actualización manual: %', p_workflow; end if;

  select x.disparado_en, x.solicitado_por, x.detalle, r.status_code
    into d
  from automatizacion.disparos x left join net._http_response r on r.id = x.request_id
  where x.workflow = p_workflow order by x.id desc limit 1;

  v_dato := automatizacion.ultimo_dato(p_workflow);
  -- NULL mientras GitHub no responde (o pg_net ya borró la respuesta); true si aceptó (204).
  v_aceptado := case when d.detalle is not null then false
                     when d.status_code is null then null
                     else d.status_code between 200 and 299 end;

  return jsonb_build_object(
    'workflow',       p_workflow,
    'nombre',         w.nombre,
    'espera_min',     w.espera_min,
    'duracion_min',   w.duracion_min,
    'ultimo_dato',    v_dato,
    'ultimo_disparo', d.disparado_en,
    'solicitado_por', d.solicitado_por,
    'aceptado',       v_aceptado,
    'detalle',        d.detalle,
    -- Hay una corrida en marcha si el último disparo es posterior a los datos y no es tan viejo como para darlo por perdido.
    'en_curso',       d.disparado_en is not null
                      and (v_dato is null or d.disparado_en > v_dato)
                      and d.disparado_en > now() - make_interval(mins => w.duracion_min * 3)
                      and coalesce(v_aceptado, true)
  );
end $$;

create or replace function public.actualizar_datos(p_workflow text)
returns jsonb language plpgsql security definer set search_path = automatizacion, public as $$
declare
  w automatizacion.workflows_manual%rowtype;
  v_ultimo timestamptz;
  v_quien text;
begin
  if auth.uid() is null then raise exception 'Hay que iniciar sesión para actualizar los datos'; end if;
  select * into w from automatizacion.workflows_manual where workflow = p_workflow;
  if not found then raise exception 'Workflow no habilitado para actualización manual: %', p_workflow; end if;

  select max(disparado_en) into v_ultimo from automatizacion.disparos where workflow = p_workflow;
  if v_ultimo is not null and v_ultimo > now() - make_interval(mins => w.espera_min) then
    return public.estado_actualizacion(p_workflow) || jsonb_build_object('ok', false,
      'motivo', format('Ya se pidió hace %s min; se puede volver a pedir en %s min.',
                       floor(extract(epoch from now() - v_ultimo) / 60)::int,
                       ceil(extract(epoch from (v_ultimo + make_interval(mins => w.espera_min) - now())) / 60)::int));
  end if;

  v_quien := coalesce(auth.jwt() ->> 'email', auth.uid()::text);
  perform automatizacion.disparar(p_workflow, w.inputs, v_quien);
  return public.estado_actualizacion(p_workflow) || jsonb_build_object('ok', true, 'motivo', null);
end $$;

revoke all on function public.estado_actualizacion(text) from public, anon;
revoke all on function public.actualizar_datos(text) from public, anon;
grant execute on function public.estado_actualizacion(text) to authenticated;
grant execute on function public.actualizar_datos(text) to authenticated;

-- Hora de la última carga de datos de un workflow, para mostrarla ("Actualizado: hoy 08:49")
-- también en los dashboards sin login (Calendario, Aceros, Plan). Solo devuelve una fecha y
-- solo para los workflows habilitados.
create or replace function public.ultima_actualizacion(p_workflow text)
returns timestamptz language plpgsql stable security definer set search_path = automatizacion, public as $$
begin
  if not exists (select 1 from automatizacion.workflows_manual where workflow = p_workflow) then
    raise exception 'Workflow no habilitado: %', p_workflow;
  end if;
  return automatizacion.ultimo_dato(p_workflow);
end $$;
revoke all on function public.ultima_actualizacion(text) from public;
grant execute on function public.ultima_actualizacion(text) to anon, authenticated;

-- La vista de control muestra también quién pidió cada corrida (se recrea: cambia la lista de columnas).
drop view if exists automatizacion.ultimos_disparos;
create or replace view automatizacion.ultimos_disparos as
select d.disparado_en at time zone 'America/Santiago' as hora_chile, d.workflow,
       coalesce(d.solicitado_por, 'pg_cron') as pedido_por,
       coalesce(d.detalle, r.status_code::text, 'pendiente') as resultado,
       left(r.content, 200) as respuesta
from automatizacion.disparos d
left join net._http_response r on r.id = d.request_id
order by d.id desc;
