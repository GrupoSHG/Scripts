-- ============================================================================
-- Oficina de Agentes: estado real de los robots + instrucciones a agentes de IA
-- ============================================================================
-- La página gruposhg-oficina (GrupoSHG_Systems/oficina-agentes/) muestra cada robot de
-- GrupoSHG/Scripts como un personaje y deja dar instrucciones a los agentes de IA. Este
-- archivo arma todo lo que esa página lee y escribe en Supabase:
--
--   1. automatizacion.corridas: las corridas de GitHub Actions de GrupoSHG/Scripts. pg_cron
--      llama cada minuto a automatizacion.sondear_corridas(), que guarda la respuesta del
--      minuto anterior y vuelve a pedir la lista a la API de GitHub (pg_net es asíncrono).
--      Usa el mismo token de Vault que disparar() (github_token, permiso Actions).
--   2. Rol agentes_lectura + public.agente_consulta(sql): los agentes de IA consultan la base
--      solo con SELECT, en una transacción de solo lectura, sin ver auth, vault ni
--      automatizacion. Solo la puede llamar service_role (el workflow agente-ia.yml).
--   3. shg_dashboards.agentes_instrucciones + public.agente_instruir(): cada instrucción queda
--      como fila y dispara agente-ia.yml con solo el id (Scripts es un repo público: el texto
--      no pasa por GitHub). El workflow escribe la respuesta en la misma fila.
--   4. public.oficina_estado(): todo lo que la página necesita en una sola llamada.
--   5. Fila 'oficina' en shg_dashboards.dashboards, solo para admin y director.
--
-- Requiere disparador_workflows.sql y actualizar_datos_manual.sql aplicados (schema
-- automatizacion, disparar() con 3 argumentos, github_token en Vault).
-- Correr en el SQL Editor del proyecto ffxopvzxyeacpbtxuagu, o por CLI:
--   supabase --workdir <tmp> db query --linked -f automatizacion/oficina_agentes.sql
-- Es idempotente. No toca programa(): el sondeo es un job de pg_cron aparte.
-- Revisar:  select * from automatizacion.corridas order by iniciada desc limit 20;
-- Pausar:   select cron.unschedule('sondear-corridas-github');
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Corridas de GitHub Actions
-- ---------------------------------------------------------------------------
create table if not exists automatizacion.corridas (
  run_id      bigint primary key,
  workflow    text not null,           -- archivo, p. ej. manager-descargas.yml
  estado      text,                    -- queued | in_progress | completed | waiting ...
  conclusion  text,                    -- success | failure | cancelled | skipped ... (null si no terminó)
  evento      text,                    -- workflow_dispatch | push ...
  iniciada    timestamptz,
  actualizada timestamptz,
  url         text
);
create index if not exists corridas_workflow_iniciada on automatizacion.corridas (workflow, iniciada desc);

create table if not exists automatizacion.sondeo_github (
  id         int primary key default 1 check (id = 1),
  request_id bigint,
  pedido_en  timestamptz
);

create or replace function automatizacion.sondear_corridas()
returns void language plpgsql security definer set search_path = automatizacion, extensions, public as $$
declare
  v_token text;
  v_req bigint;
  r record;
begin
  -- 1) Guardar la respuesta que pidió la llamada anterior (pg_net la deja en net._http_response).
  select request_id into v_req from automatizacion.sondeo_github where id = 1;
  if v_req is not null then
    select status_code, content into r from net._http_response where id = v_req;
    if found and r.status_code = 200 then
      insert into automatizacion.corridas (run_id, workflow, estado, conclusion, evento, iniciada, actualizada, url)
      select (x->>'id')::bigint, regexp_replace(x->>'path', '^.*/', ''), x->>'status', x->>'conclusion',
             x->>'event', (x->>'run_started_at')::timestamptz, (x->>'updated_at')::timestamptz, x->>'html_url'
        from jsonb_array_elements(r.content::jsonb -> 'workflow_runs') x
      on conflict (run_id) do update
        set estado = excluded.estado, conclusion = excluded.conclusion, iniciada = excluded.iniciada,
            actualizada = excluded.actualizada, url = excluded.url;
    end if;
  end if;

  -- 2) Pedir la lista de nuevo.
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'github_token' limit 1;
  if v_token is null then return; end if;
  select net.http_get(
    url := 'https://api.github.com/repos/GrupoSHG/Scripts/actions/runs?per_page=40',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || v_token,
      'Accept', 'application/vnd.github+json',
      'X-GitHub-Api-Version', '2022-11-28',
      'User-Agent', 'polchile-supabase-cron'),
    timeout_milliseconds := 10000
  ) into v_req;
  insert into automatizacion.sondeo_github (id, request_id, pedido_en) values (1, v_req, now())
  on conflict (id) do update set request_id = excluded.request_id, pedido_en = excluded.pedido_en;

  delete from automatizacion.corridas where iniciada < now() - interval '30 days';
end $$;
revoke all on function automatizacion.sondear_corridas() from public, anon, authenticated;

select cron.unschedule('sondear-corridas-github') where exists (select 1 from cron.job where jobname = 'sondear-corridas-github');
select cron.schedule('sondear-corridas-github', '* * * * *', 'select automatizacion.sondear_corridas()');

-- ---------------------------------------------------------------------------
-- 2. Lectura para los agentes de IA
-- ---------------------------------------------------------------------------
-- Rol sin login que solo tiene SELECT sobre los esquemas de datos del negocio. Ve todas las
-- filas (bypassrls) porque la oficina es solo para admin y director, que ya ven todo.
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'agentes_lectura') then
    create role agentes_lectura nologin bypassrls;
  end if;
end $$;

do $$
declare s text;
begin
  foreach s in array array['shg_dashboards', 'polchile_crm', 'm5', 'app_cys', 'stock_productos', 'hea'] loop
    execute format('grant usage on schema %I to agentes_lectura', s);
    execute format('grant select on all tables in schema %I to agentes_lectura', s);
    -- El pipeline borra y recrea tablas todos los días (como postgres): las nuevas también.
    execute format('alter default privileges for role postgres in schema %I grant select on tables to agentes_lectura', s);
  end loop;
end $$;
-- Lo de las cuentas de usuario no le sirve a ningún agente.
revoke select on hea.profiles, stock_productos.profiles from agentes_lectura;

-- Para ser dueño de la función de abajo el rol necesita CREATE en public. No puede usarlo:
-- todo lo que corre como agentes_lectura va dentro de una transacción de solo lectura.
grant usage, create on schema public to agentes_lectura;

create or replace function public.agente_consulta(p_sql text, p_limite int default 200)
returns jsonb language plpgsql security definer set search_path = pg_catalog, public as $$
declare
  v_sql text := regexp_replace(btrim(p_sql), ';+\s*$', '');
  v_limite int := least(greatest(coalesce(p_limite, 200), 1), 500);
  v_filas jsonb;
begin
  if v_sql !~* '^(select|with)\s' then
    raise exception 'Solo se permiten consultas SELECT (o WITH ... SELECT).';
  end if;
  -- Pasar a solo lectura sí se permite a mitad de transacción; volver atrás no.
  perform set_config('transaction_read_only', 'on', true);
  execute format('select coalesce(jsonb_agg(t), ''[]''::jsonb) from (select * from (%s) q limit %s) t', v_sql, v_limite)
    into v_filas;
  return jsonb_build_object('filas', v_filas, 'n', jsonb_array_length(v_filas), 'limite', v_limite);
end $$;
-- Desde Postgres 16 quien crea un rol no puede hacer SET ROLE a él sin membresía explícita, y
-- ALTER ... OWNER lo exige: se da solo para el cambio de dueño y se quita al tiro.
do $$ begin execute format('grant agentes_lectura to %I with inherit false, set true', current_user); end $$;
alter function public.agente_consulta(text, int) owner to agentes_lectura;
do $$ begin execute format('revoke agentes_lectura from %I', current_user); end $$;
revoke all on function public.agente_consulta(text, int) from public, anon, authenticated;
grant execute on function public.agente_consulta(text, int) to service_role;

-- ---------------------------------------------------------------------------
-- 3. Instrucciones a los agentes de IA
-- ---------------------------------------------------------------------------
create table if not exists shg_dashboards.agentes_instrucciones (
  id             bigint generated always as identity primary key,
  agente         text not null check (agente in ('comercial', 'finanzas', 'planta', 'dev', 'dev2', 'dev3', 'dev4')),
  texto          text not null check (length(texto) between 3 and 4000),
  parametros     jsonb not null default '{}'::jsonb,   -- dev: {"repo": "GrupoSHG_Systems" | "Scripts"}
  estado         text not null default 'pendiente' check (estado in ('pendiente', 'trabajando', 'listo', 'error')),
  pedido_por     text,
  pedido_por_uid uuid,
  creada         timestamptz not null default now(),
  iniciada       timestamptz,
  terminada      timestamptz,
  respuesta      text,
  error          text,
  costo_usd      numeric(10, 4) not null default 0,
  tokens         jsonb,
  run_url        text
);
create index if not exists agentes_instrucciones_creada on shg_dashboards.agentes_instrucciones (creada desc);

alter table shg_dashboards.agentes_instrucciones enable row level security;
revoke all on shg_dashboards.agentes_instrucciones from anon, authenticated;
grant select on shg_dashboards.agentes_instrucciones to authenticated;
drop policy if exists solo_directores on shg_dashboards.agentes_instrucciones;
create policy solo_directores on shg_dashboards.agentes_instrucciones
  for select to authenticated using ((select shg_dashboards.es_director()));
-- Los agentes no leen sus propias instrucciones ni las de otros.
revoke select on shg_dashboards.agentes_instrucciones from agentes_lectura;

create or replace function public.agente_instruir(p_agente text, p_texto text, p_parametros jsonb default '{}'::jsonb)
returns jsonb language plpgsql security definer set search_path = shg_dashboards, automatizacion, public as $$
declare
  v_id bigint;
  v_quien text := coalesce(auth.jwt() ->> 'email', auth.uid()::text);
  v_abiertas int;
begin
  if auth.uid() is null then raise exception 'Hay que iniciar sesión'; end if;
  if not shg_dashboards.es_director() then
    raise exception 'Solo admin y directores pueden dar instrucciones a los agentes' using errcode = '42501';
  end if;
  select count(*) into v_abiertas from shg_dashboards.agentes_instrucciones
   where estado in ('pendiente', 'trabajando') and creada > now() - interval '1 hour';
  if v_abiertas >= 10 then
    raise exception 'Ya hay % instrucciones en curso; espera a que terminen.', v_abiertas;
  end if;

  insert into shg_dashboards.agentes_instrucciones (agente, texto, parametros, pedido_por, pedido_por_uid)
  values (p_agente, btrim(p_texto), coalesce(p_parametros, '{}'::jsonb), v_quien, auth.uid())
  returning id into v_id;

  perform automatizacion.disparar('agente-ia.yml', jsonb_build_object('instruccion', v_id::text), v_quien);
  return jsonb_build_object('ok', true, 'id', v_id);
end $$;
revoke all on function public.agente_instruir(text, text, jsonb) from public, anon;
grant execute on function public.agente_instruir(text, text, jsonb) to authenticated;

-- ---------------------------------------------------------------------------
-- 4. Todo lo que muestra la oficina, en una llamada
-- ---------------------------------------------------------------------------
create or replace function public.oficina_estado()
returns jsonb language plpgsql stable security definer set search_path = automatizacion, shg_dashboards, public as $$
begin
  if auth.uid() is null or not shg_dashboards.es_director() then
    raise exception 'La oficina de agentes es solo para admin y directores' using errcode = '42501';
  end if;
  return jsonb_build_object(
    'ahora', now(),
    'sondeo', (select pedido_en from automatizacion.sondeo_github where id = 1),
    -- Última corrida de cada workflow, la última exitosa y si la anterior falló.
    'robots', coalesce((
      select jsonb_agg(jsonb_build_object(
        'workflow', u.workflow, 'estado', u.estado, 'conclusion', u.conclusion, 'iniciada', u.iniciada,
        'actualizada', u.actualizada, 'url', u.url,
        'ultimo_ok', (select max(c.iniciada) from automatizacion.corridas c
                       where c.workflow = u.workflow and c.conclusion = 'success'),
        'hoy', (select count(*) from automatizacion.corridas c
                 where c.workflow = u.workflow
                   and c.iniciada >= date_trunc('day', now() at time zone 'America/Santiago') at time zone 'America/Santiago'),
        'manual', exists (select 1 from automatizacion.workflows_manual m where m.workflow = u.workflow)))
      from (select distinct on (workflow) * from automatizacion.corridas order by workflow, iniciada desc) u), '[]'::jsonb),
    -- Último disparo de cada workflow (pg_cron o botón), por si GitHub todavía no lo muestra.
    'disparos', coalesce((
      select jsonb_agg(jsonb_build_object('workflow', d.workflow, 'en', d.disparado_en,
                                          'pedido_por', coalesce(d.solicitado_por, 'pg_cron')))
      from (select distinct on (workflow) * from automatizacion.disparos
             where disparado_en > now() - interval '1 day' order by workflow, id desc) d), '[]'::jsonb),
    -- Resúmenes diarios: corren en el repo privado resumenes-diarios, no en Scripts.
    'resumenes', coalesce((
      select jsonb_agg(jsonb_build_object('area', r.area, 'ejecutado_en', r.ejecutado_en, 'valido', r.valido))
      from (select distinct on (area) area, ejecutado_en, valido from shg_dashboards.resumenes_diarios
             order by area, ejecutado_en desc) r), '[]'::jsonb),
    'instrucciones', coalesce((
      select jsonb_agg(to_jsonb(i) - 'pedido_por_uid' order by i.id desc)
      from (select * from shg_dashboards.agentes_instrucciones order by id desc limit 60) i), '[]'::jsonb)
  );
end $$;
revoke all on function public.oficina_estado() from public, anon;
grant execute on function public.oficina_estado() to authenticated;

-- ---------------------------------------------------------------------------
-- 5. La página en la matriz de accesos: solo admin y director
-- ---------------------------------------------------------------------------
insert into shg_dashboards.dashboards (codigo, nombre, empresa, area, url, orden)
values ('oficina', 'Oficina de Agentes', 'grupo', 'direccion', 'https://gruposhg-oficina.netlify.app/', 90)
on conflict (codigo) do update set nombre = excluded.nombre, url = excluded.url, orden = excluded.orden;
insert into shg_dashboards.permisos_rol (rol, dashboard, alcance, solo_su_area)
values ('admin', 'oficina', 'todo', false), ('director', 'oficina', 'todo', false)
on conflict (rol, dashboard) do nothing;

notify pgrst, 'reload schema';
