-- Evaluación con Claude en m5.licitaciones_mp + rol de permisos mínimos para el proceso diario.
-- Lo usa M5_Systems/licitaciones-m5 (comando `guardar`) y lo muestra
-- GrupoSHG_Systems/M5_Systems/proyectos/licitaciones.html.
-- Se aplica a mano (SQL Editor o `supabase --workdir <tmp> db query --linked -f`); es idempotente.
-- La tabla base está definida en licitaciones_mp.sql (misma carpeta).

-- 1. Columnas de la evaluación (null = todavía no evaluada, p. ej. las que cargó el job antiguo)
alter table m5.licitaciones_mp
  add column if not exists puntaje           smallint,
  add column if not exists recomendacion     text,
  add column if not exists estado_evaluacion text,
  add column if not exists motivo            text,
  add column if not exists tipo_de_obra      text,
  add column if not exists requisitos_clave  text[] not null default '{}',
  add column if not exists riesgos           text[] not null default '{}',
  add column if not exists modelo_evaluacion text,
  add column if not exists evaluado_en       timestamptz;

alter table m5.licitaciones_mp drop constraint if exists licitaciones_mp_puntaje_chk;
alter table m5.licitaciones_mp add constraint licitaciones_mp_puntaje_chk check (puntaje between 1 and 5);
alter table m5.licitaciones_mp drop constraint if exists licitaciones_mp_recomendacion_chk;
alter table m5.licitaciones_mp add constraint licitaciones_mp_recomendacion_chk
  check (recomendacion in ('postular', 'revisar', 'descartar'));
alter table m5.licitaciones_mp drop constraint if exists licitaciones_mp_estado_evaluacion_chk;
alter table m5.licitaciones_mp add constraint licitaciones_mp_estado_evaluacion_chk
  check (estado_evaluacion in ('ok', 'revisar_manualmente'));

comment on column m5.licitaciones_mp.recomendacion is
  'postular / revisar / descartar según Claude. Las "descartar" se guardan solo para no volver a evaluarlas; la página no las muestra.';

-- 2. Rol del proceso diario: solo leer, insertar y actualizar esta tabla (sin borrar, sin otras tablas).
--    La clave SUPABASE_KEY es un JWT con "role": "licitaciones_m5" firmado con el JWT secret del proyecto
--    (lo genera el usuario con generar_clave_supabase.py; nunca pasa por el repo).
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'licitaciones_m5') then
    create role licitaciones_m5 nologin noinherit;
  end if;
end $$;
grant licitaciones_m5 to authenticator;
grant usage on schema m5 to licitaciones_m5;
grant select, insert, update on m5.licitaciones_mp to licitaciones_m5;

drop policy if exists proceso_licitaciones_m5 on m5.licitaciones_mp;
create policy proceso_licitaciones_m5 on m5.licitaciones_mp for all to licitaciones_m5
  using (true) with check (true);

select count(*) as filas,
       count(*) filter (where puntaje is not null) as evaluadas,
       (select count(*) from pg_roles where rolname = 'licitaciones_m5') as rol_creado
from m5.licitaciones_mp;
