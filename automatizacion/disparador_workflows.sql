-- ============================================================================
-- Disparador de workflows de GrupoSHG/Scripts desde Supabase (pg_cron + pg_net)
-- ============================================================================
-- Por qué: el "schedule" de GitHub Actions llega con 4–7 h de atraso y se salta
-- corridas (el pipeline programado 06:45 partía entre 10:30 y 14:15; el
-- monitoreo horario corrió 1 de 12 veces). pg_cron es puntual al minuto.
--
-- Qué hace: cada minuto, automatizacion.programa() mira la hora de Santiago y,
-- cuando corresponde, llama a la API de GitHub (workflow_dispatch):
--   pipeline.yml            lun-vie 06:30
--   manager-descargas.yml   lun-vie 09:07 a 18:07, cada hora
--   bitacora-alertas.yml    lun-vie 09:03 a 18:03, cada hora
--   monitoreo.yml           todos los días, cada 4 h (00:17, 04:17, ... 20:17)
--   m5-ghl-sync.yml         todos los días, cada 4 h (08:12, 12:12, 16:12, 20:12)
--   ghl-polchile-sync.yml   todos los días, cada 4 h (08:22, 12:22, 16:22, 20:22)
--
-- Cadencia de 4 h (02-10-2026): si el repo pasa a privado, GitHub cobra los minutos
-- de Actions sobre los 2.000 gratis al mes. Monitoreo y los dos syncs de CRM cada
-- hora sumaban ~3.800 min/mes; cada 4 h quedan en ~1.000. El botón "Actualizar
-- datos" de los dashboards sigue disparando una corrida al instante.
--
-- Antes de correr esto, guardar el token en Vault (fine-grained PAT con owner
-- GrupoSHG, solo el repo Scripts, permiso Actions: Read and write):
--   select vault.create_secret('github_pat_...', 'github_token');
--
-- Correr en el SQL Editor del proyecto ffxopvzxyeacpbtxuagu.
-- Para revisar:   select * from automatizacion.ultimos_disparos limit 20;   (204 = aceptado)
-- Para pausar:    select cron.unschedule('disparar-workflows-github');
-- ============================================================================

create extension if not exists pg_cron;

create schema if not exists automatizacion;
revoke all on schema automatizacion from public, anon, authenticated;

create table if not exists automatizacion.disparos (
  id bigint generated always as identity primary key,
  workflow text not null,
  request_id bigint,
  detalle text,
  disparado_en timestamptz not null default now()
);

create or replace function automatizacion.disparar(p_workflow text, p_inputs jsonb default '{}'::jsonb)
returns void language plpgsql security definer set search_path = automatizacion, extensions, public as $$
declare
  v_token text;
  v_req bigint;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'github_token' limit 1;
  if v_token is null then
    insert into automatizacion.disparos (workflow, detalle) values (p_workflow, 'sin token: falta el secret github_token en Vault');
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
  insert into automatizacion.disparos (workflow, request_id) values (p_workflow, v_req);
end $$;

-- Programa en hora de Santiago (el cambio de horario lo resuelve la zona horaria).
create or replace function automatizacion.programa()
returns void language plpgsql security definer set search_path = automatizacion, public as $$
declare
  t timestamp := now() at time zone 'America/Santiago';
  h int := extract(hour from t);
  mi int := extract(minute from t);
  habil boolean := extract(isodow from t) <= 5;
begin
  if habil and h = 6 and mi = 30 then
    perform automatizacion.disparar('pipeline.yml');
  end if;
  if habil and h between 9 and 18 and mi = 7 then
    perform automatizacion.disparar('manager-descargas.yml', '{"forzar": "true", "sin_cargar": "false"}');
  end if;
  if habil and h between 9 and 18 and mi = 3 then
    perform automatizacion.disparar('bitacora-alertas.yml', '{"forzar": "false"}');
  end if;
  if h % 4 = 0 and mi = 17 then
    perform automatizacion.disparar('monitoreo.yml', '{"forzar": "false"}');
  end if;
  if h in (8, 12, 16, 20) and mi = 12 then
    perform automatizacion.disparar('m5-ghl-sync.yml');
  end if;
  if h in (8, 12, 16, 20) and mi = 22 then
    perform automatizacion.disparar('ghl-polchile-sync.yml');
  end if;
end $$;

revoke all on function automatizacion.disparar(text, jsonb) from public, anon, authenticated;
revoke all on function automatizacion.programa() from public, anon, authenticated;

create or replace view automatizacion.ultimos_disparos as
select d.disparado_en at time zone 'America/Santiago' as hora_chile, d.workflow,
       coalesce(d.detalle, r.status_code::text, 'pendiente') as resultado,
       left(r.content, 200) as respuesta
from automatizacion.disparos d
left join net._http_response r on r.id = d.request_id
order by d.id desc;

select cron.schedule('disparar-workflows-github', '* * * * *', 'select automatizacion.programa()');
