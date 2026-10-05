-- ============================================================================
-- Carga del CRM Polchile (GoHighLevel) en Supabase, schema polchile_crm
-- ============================================================================
-- Lo usa polchile/sync_ghl_polchile.py (workflow ghl-polchile-sync):
--   iniciar_carga()            vacía las tablas de carga (carga_*)
--   cargar_lote(tabla, filas)  agrega un lote de hasta 1.000 filas a carga_<tabla>
--   publicar_carga()           intercambia por nombre las tablas de carga con las
--                              publicadas (pipeline_etapas / usuarios / oportunidades /
--                              contactos), en una sola transacción
--
-- Por qué intercambio y no DELETE + INSERT: PostgREST corta cualquier llamada que
-- pase de 8 s (statement_timeout del rol authenticator) y copiar ~45.000 filas con
-- jsonb tarda 20-35 s en esta base (error 57014 "canceling statement due to
-- statement timeout" desde el 01/10/2026 19:22). Renombrar tablas es instantáneo y
-- no depende del tamaño del CRM. Para eso las tablas carga_* son idénticas a las
-- publicadas: mismas columnas, NOT NULL, índices, permisos y política RLS. Los
-- índices conservan su nombre original, así que uno llamado oportunidades_* puede
-- estar en carga_oportunidades (no afecta a nada).
--
-- Ya aplicado en el proyecto ffxopvzxyeacpbtxuagu (migraciones
-- polchile_crm_publicar_carga_rapido y polchile_crm_publicar_por_intercambio).
-- El RPC del dashboard está en GrupoSHG_Systems/polchile/comercial-crm/resumen_dashboard.sql.
-- ============================================================================

-- Tablas de carga idénticas a las publicadas
alter table polchile_crm.carga_pipeline_etapas add primary key (etapa_id), alter column pipeline_id set not null;
alter table polchile_crm.carga_usuarios add primary key (id);
alter table polchile_crm.carga_oportunidades add primary key (id), alter column campos set not null;
create index carga_oportunidades_pipeline_id_estado_idx on polchile_crm.carga_oportunidades (pipeline_id, estado);
create index carga_oportunidades_creada_en_idx on polchile_crm.carga_oportunidades (creada_en);
alter table polchile_crm.carga_contactos add primary key (id), alter column campos set not null;
create index carga_contactos_creado_en_idx on polchile_crm.carga_contactos (creado_en);

grant select on polchile_crm.carga_pipeline_etapas, polchile_crm.carga_usuarios,
                polchile_crm.carga_oportunidades, polchile_crm.carga_contactos to authenticated;
create policy lectura_autenticados on polchile_crm.carga_pipeline_etapas for select to authenticated using (true);
create policy lectura_autenticados on polchile_crm.carga_usuarios         for select to authenticated using (true);
create policy lectura_autenticados on polchile_crm.carga_oportunidades    for select to authenticated using (true);
create policy lectura_autenticados on polchile_crm.carga_contactos        for select to authenticated using (true);

create or replace function polchile_crm.iniciar_carga()
returns void language plpgsql security definer set search_path to 'polchile_crm' as $$
begin
  truncate carga_pipeline_etapas, carga_usuarios, carga_oportunidades, carga_contactos;
end $$;

create or replace function polchile_crm.cargar_lote(tabla text, filas jsonb)
returns integer language plpgsql set search_path to 'polchile_crm' as $$
declare n int; ahora jsonb := jsonb_build_object('sincronizado_en', now());
begin
  -- jsonb_populate_recordset deja NULL las columnas que no vienen en el JSON (el default no
  -- aplica), por eso la hora de sincronización se agrega aquí a cada fila.
  -- on conflict: un lote reintentado tras un error 5xx puede venir dos veces.
  if tabla = 'pipeline_etapas' then
    insert into carga_pipeline_etapas
    select * from jsonb_populate_recordset(null::carga_pipeline_etapas,
      (select jsonb_agg(f || jsonb_build_object('actualizado_en', now())) from jsonb_array_elements(filas) f))
    on conflict (etapa_id) do nothing;
  elsif tabla = 'usuarios' then
    insert into carga_usuarios select * from jsonb_populate_recordset(null::carga_usuarios, filas)
    on conflict (id) do nothing;
  elsif tabla = 'oportunidades' then
    insert into carga_oportunidades
    select * from jsonb_populate_recordset(null::carga_oportunidades,
      (select jsonb_agg(f || ahora) from jsonb_array_elements(filas) f))
    on conflict (id) do nothing;
  elsif tabla = 'contactos' then
    insert into carga_contactos
    select * from jsonb_populate_recordset(null::carga_contactos,
      (select jsonb_agg(f || ahora) from jsonb_array_elements(filas) f))
    on conflict (id) do nothing;
  else
    raise exception 'Tabla desconocida: %', tabla;
  end if;
  get diagnostics n = row_count;
  return n;
end $$;

create or replace function polchile_crm.publicar_carga()
returns jsonb language plpgsql security definer set search_path to 'polchile_crm' as $$
declare r jsonb;
begin
  if not exists (select 1 from carga_oportunidades) then
    raise exception 'La carga no trae oportunidades: no se reemplaza polchile_crm';
  end if;
  if not exists (select 1 from carga_pipeline_etapas) then
    raise exception 'La carga no trae etapas de pipeline: no se reemplaza polchile_crm';
  end if;
  -- Intercambio por nombre, en una transacción: lo cargado pasa a ser la tabla publicada y la
  -- tabla anterior queda como tabla de carga (se vacía al final).
  alter table pipeline_etapas rename to intercambio_tmp;
  alter table carga_pipeline_etapas rename to pipeline_etapas;
  alter table intercambio_tmp rename to carga_pipeline_etapas;
  alter table usuarios rename to intercambio_tmp;
  alter table carga_usuarios rename to usuarios;
  alter table intercambio_tmp rename to carga_usuarios;
  alter table oportunidades rename to intercambio_tmp;
  alter table carga_oportunidades rename to oportunidades;
  alter table intercambio_tmp rename to carga_oportunidades;
  alter table contactos rename to intercambio_tmp;
  alter table carga_contactos rename to contactos;
  alter table intercambio_tmp rename to carga_contactos;
  r := jsonb_build_object('etapas', (select count(*) from pipeline_etapas), 'usuarios', (select count(*) from usuarios),
                          'oportunidades', (select count(*) from oportunidades), 'contactos', (select count(*) from contactos));
  truncate carga_pipeline_etapas, carga_usuarios, carga_oportunidades, carga_contactos;
  return r;
end $$;

-- Solo el workflow (service_role) puede cargar y publicar; el dashboard solo lee.
revoke all on function polchile_crm.iniciar_carga() from public, anon, authenticated;
revoke all on function polchile_crm.cargar_lote(text, jsonb) from public, anon, authenticated;
revoke all on function polchile_crm.publicar_carga() from public, anon, authenticated;
grant execute on function polchile_crm.iniciar_carga() to service_role;
grant execute on function polchile_crm.cargar_lote(text, jsonb) to service_role;
grant execute on function polchile_crm.publicar_carga() to service_role;
