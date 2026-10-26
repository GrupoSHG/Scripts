-- Bases de licitaciones (PDF subidos por M5), materiales extraídos con Claude y costo estimado.
-- La página licitaciones.html (GrupoSHG_Systems/M5_Systems/proyectos) sube los PDF y pide el
-- procesamiento; M5_Systems/licitaciones-m5 (comando `bases`, workflow licitaciones-bases.yml) los lee
-- con el rol licitaciones_m5. Se aplica a mano; es idempotente.
-- Requiere licitaciones_mp_evaluacion.sql (rol licitaciones_m5) y precios_oc.sql (precios de referencia).

-- 1. Almacenamiento privado, solo PDF, hasta 50 MB por archivo.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('licitaciones-bases', 'licitaciones-bases', false, 52428800, array['application/pdf'])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit,
                               allowed_mime_types = excluded.allowed_mime_types;

-- El equipo con sesión (no los clientes externos de M5) sube y descarga; nadie borra desde la página.
drop policy if exists licitaciones_bases_leer on storage.objects;
create policy licitaciones_bases_leer on storage.objects for select to authenticated
  using (bucket_id = 'licitaciones-bases' and coalesce(shg_dashboards.rol_actual(), '') <> 'cliente');
drop policy if exists licitaciones_bases_subir on storage.objects;
create policy licitaciones_bases_subir on storage.objects for insert to authenticated
  with check (bucket_id = 'licitaciones-bases' and coalesce(shg_dashboards.rol_actual(), '') <> 'cliente');

-- El proceso (rol licitaciones_m5) solo lee ese bucket.
grant usage on schema storage to licitaciones_m5;
grant select on storage.objects, storage.buckets to licitaciones_m5;
drop policy if exists licitaciones_bases_proceso on storage.objects;
create policy licitaciones_bases_proceso on storage.objects for select to licitaciones_m5
  using (bucket_id = 'licitaciones-bases');
drop policy if exists licitaciones_bases_proceso on storage.buckets;
create policy licitaciones_bases_proceso on storage.buckets for select to licitaciones_m5
  using (id = 'licitaciones-bases');

-- 2. Un PDF subido por fila, con su estado de procesamiento.
create table if not exists m5.licitaciones_bases (
  id              bigint generated always as identity primary key,
  codigo_externo  text not null references m5.licitaciones_mp (codigo_externo) on delete cascade,
  ruta            text not null unique,                 -- ruta en el bucket licitaciones-bases
  nombre_archivo  text not null,
  bytes           bigint,
  subido_por      uuid not null default auth.uid(),
  subido_nombre   text,
  subido_en       timestamptz not null default now(),
  estado          text not null default 'pendiente'
                  check (estado in ('pendiente', 'procesando', 'listo', 'error')),
  error           text,
  procesado_en    timestamptz,
  tokens_entrada  int,
  costo_usd       numeric
);
create index if not exists licitaciones_bases_codigo_idx on m5.licitaciones_bases (codigo_externo);
create index if not exists licitaciones_bases_estado_idx on m5.licitaciones_bases (estado);

-- 3. Materiales que Claude extrae de cada PDF. Cantidad y unidad tal como están escritas; la conversión a
--    unidad base la hace el código (igual que en precios_oc_items).
create table if not exists m5.licitaciones_materiales (
  id                bigint generated always as identity primary key,
  base_id           bigint not null references m5.licitaciones_bases (id) on delete cascade,
  codigo_externo    text not null,
  item              text not null,          -- descripción como aparece en las bases
  material          text,                   -- nombre genérico (mismo vocabulario que precios_oc_items)
  especificacion    text,
  cantidad          numeric,
  unidad            text,
  cantidad_base     numeric,
  unidad_base       text check (unidad_base in ('unidad', 'kg', 'm', 'm2', 'm3', 'litro')),
  pagina            int,
  confianza         text check (confianza in ('alta', 'media', 'baja')),
  creado_en         timestamptz not null default now()
);
create index if not exists licitaciones_materiales_codigo_idx on m5.licitaciones_materiales (codigo_externo);

-- 4. Precio de referencia por material y unidad base (todas las especificaciones juntas), 90 días.
create or replace view m5.precios_material_base with (security_invoker = true) as
select material, unidad_base, count(*) as n,
       percentile_cont(0.5) within group (order by precio_unidad_base) as mediana_unidad_base,
       max(fecha_envio) as hasta
  from m5.precios_oc_items
 where es_material_construccion and confianza in ('alta', 'media')
   and material is not null and unidad_base is not null and precio_unidad_base is not null
   and fecha_envio >= now() - interval '90 days'
 group by 1, 2;

-- 5. Cada material con su precio de referencia y total estimado (null si no hay precio en esa unidad).
create or replace view m5.licitaciones_materiales_costo with (security_invoker = true) as
select m.*, p.mediana_unidad_base as precio_referencia, p.n as compras_referencia, p.hasta as precio_hasta,
       round((m.cantidad_base * p.mediana_unidad_base)::numeric) as total_estimado
  from m5.licitaciones_materiales m
  left join m5.precios_material_base p on p.material = m.material and p.unidad_base = m.unidad_base;

-- 6. Resumen por licitación para la tabla principal.
create or replace view m5.licitaciones_costo_estimado with (security_invoker = true) as
select codigo_externo,
       count(*)                                          as materiales,
       count(*) filter (where total_estimado is not null) as con_precio,
       round(100.0 * count(*) filter (where total_estimado is not null) / nullif(count(*), 0)) as cobertura_pct,
       sum(total_estimado)                               as total_estimado
  from m5.licitaciones_materiales_costo
 group by 1;

-- 7. Acceso. Equipo: lee todo, inserta bases a su nombre. Proceso: lee bases, cambia su estado y reemplaza
--    los materiales de cada PDF.
alter table m5.licitaciones_bases enable row level security;
alter table m5.licitaciones_materiales enable row level security;
revoke all on m5.licitaciones_bases, m5.licitaciones_materiales from anon, public;
grant select, insert on m5.licitaciones_bases to authenticated;
grant select on m5.licitaciones_materiales to authenticated;
grant select, update on m5.licitaciones_bases to licitaciones_m5;
grant select, insert, delete on m5.licitaciones_materiales to licitaciones_m5;
revoke all on m5.precios_material_base, m5.licitaciones_materiales_costo, m5.licitaciones_costo_estimado
  from anon, public;
grant select on m5.precios_material_base, m5.licitaciones_materiales_costo, m5.licitaciones_costo_estimado
  to authenticated, licitaciones_m5;

drop policy if exists lectura_autenticados on m5.licitaciones_bases;
create policy lectura_autenticados on m5.licitaciones_bases for select to authenticated using (true);
drop policy if exists subir_bases on m5.licitaciones_bases;
create policy subir_bases on m5.licitaciones_bases for insert to authenticated
  with check (subido_por = auth.uid() and estado = 'pendiente');
drop policy if exists proceso_licitaciones_m5 on m5.licitaciones_bases;
create policy proceso_licitaciones_m5 on m5.licitaciones_bases for all to licitaciones_m5 using (true) with check (true);

drop policy if exists lectura_autenticados on m5.licitaciones_materiales;
create policy lectura_autenticados on m5.licitaciones_materiales for select to authenticated using (true);
drop policy if exists proceso_licitaciones_m5 on m5.licitaciones_materiales;
create policy proceso_licitaciones_m5 on m5.licitaciones_materiales for all to licitaciones_m5 using (true) with check (true);

drop policy if exists sin_clientes_externos on m5.licitaciones_bases;
create policy sin_clientes_externos on m5.licitaciones_bases as restrictive for all to authenticated
  using (coalesce(shg_dashboards.rol_actual(), '') <> 'cliente')
  with check (coalesce(shg_dashboards.rol_actual(), '') <> 'cliente');
drop policy if exists sin_clientes_externos on m5.licitaciones_materiales;
create policy sin_clientes_externos on m5.licitaciones_materiales as restrictive for all to authenticated
  using (coalesce(shg_dashboards.rol_actual(), '') <> 'cliente');

-- 8. Botón "Procesar bases" de la página: dispara licitaciones-bases.yml por el mismo mecanismo que
--    "Actualizar datos" (public.actualizar_datos). Espera de 2 min entre pedidos.
insert into automatizacion.workflows_manual (workflow, nombre, inputs, espera_min, duracion_min)
values ('licitaciones-bases.yml', 'Bases de licitaciones M5 (materiales y costo estimado)', '{}', 2, 5)
on conflict (workflow) do update set nombre = excluded.nombre, espera_min = excluded.espera_min,
                                     duracion_min = excluded.duracion_min;

-- ultimo_dato: se agrega solo el caso nuevo; el resto es el que estaba en vivo el 26/10/2026.
create or replace function automatizacion.ultimo_dato(p_workflow text)
 returns timestamp with time zone language sql stable security definer
 set search_path to 'automatizacion', 'public'
as $function$
  select case p_workflow
    when 'manager-descargas.yml' then shg_dashboards.ultima_carga_manager()
    when 'ghl-polchile-sync.yml' then (select max(sincronizado_en) from polchile_crm.oportunidades)
    when 'm5-ghl-sync.yml'       then (select max(sincronizado_en) from m5.oportunidades)
    when 'pipeline.yml'          then greatest(
        (select max(actualizado_en) from shg_dashboards.notas_venta_pendientes),
        (select max(actualizado_en) from shg_dashboards.facturacion_periodo))
    when 'licitaciones-bases.yml' then (select max(procesado_en) from m5.licitaciones_bases)
  end;
$function$;

select (select count(*) from storage.buckets where id = 'licitaciones-bases') as bucket,
       (select count(*) from m5.licitaciones_bases) as bases,
       (select count(*) from m5.precios_material_base) as materiales_con_precio;
