-- =====================================================================
-- compras_importacion.sql  (se aplica a mano en el SQL Editor de Supabase)
-- Proyecto ffxopvzxyeacpbtxuagu, esquema shg_dashboards. Idempotente.
--
-- Registro de qué facturas de compra del RCV del SII se subieron a Manager
-- desde la pantalla RCV · SII del Dashboard Finanzas (rcv-manager.js):
--   preparada  = se incluyó en un archivo de importación descargado
--   importada  = alguien confirmó en la pantalla que la importó en Manager
-- El tercer estado, "en Manager", no se guarda aquí: lo da la copia diaria
-- de Manager (compras_manager_docs, ver compras_manager.sql) y la vista
-- compras_estado_manager lo combina con este registro.
-- Escriben solo los usuarios con acceso a Finanzas (public.puede_ver), a
-- través de public.marcar_compras_manager / desmarcar_compra_manager.
-- =====================================================================

create table if not exists shg_dashboards.compras_importacion (
    empresa        text        not null default 'polchile',
    rut            text        not null,           -- sin puntos, con guión, mayúsculas
    docto          text        not null,           -- FAC | NCC (tipo de Manager)
    folio          bigint      not null,
    estado         text        not null check (estado in ('preparada', 'importada')),
    razon_social   text,
    fecha_doc      date,
    total          numeric,
    archivo        text,                           -- nombre del último archivo que la incluyó
    preparado_por  text,
    preparado_en   timestamptz,
    importado_por  text,
    importado_en   timestamptz,
    primary key (empresa, rut, docto, folio)
);
create index if not exists compras_importacion_folio_idx on shg_dashboards.compras_importacion (folio);

alter table shg_dashboards.compras_importacion enable row level security;
drop policy if exists compras_importacion_lectura on shg_dashboards.compras_importacion;
create policy compras_importacion_lectura on shg_dashboards.compras_importacion
  for select to authenticated using (public.puede_ver('finanzas') is not null);
revoke all on shg_dashboards.compras_importacion from anon;
grant select on shg_dashboards.compras_importacion to authenticated;
grant all on shg_dashboards.compras_importacion to service_role;

-- Marca documentos. p_documentos: [{rut, docto, folio, razon_social, fecha, total}, ...]
-- 'preparada' no rebaja a una que ya estaba 'importada'.
create or replace function public.marcar_compras_manager(p_empresa text, p_estado text, p_documentos jsonb, p_archivo text default null)
returns int language plpgsql security definer set search_path = shg_dashboards, public as $$
declare
  v_usuario text := coalesce(auth.jwt() ->> 'email', 'usuario');
  v_n int;
begin
  if public.puede_ver('finanzas') is null then
    raise exception 'Sin acceso a Finanzas';
  end if;
  if p_estado not in ('preparada', 'importada') then
    raise exception 'Estado inválido: %', p_estado;
  end if;
  insert into shg_dashboards.compras_importacion as ci
    (empresa, rut, docto, folio, estado, razon_social, fecha_doc, total, archivo,
     preparado_por, preparado_en, importado_por, importado_en)
  select coalesce(p_empresa, 'polchile'),
         upper(replace(trim(d->>'rut'), '.', '')), d->>'docto', (d->>'folio')::bigint, p_estado,
         d->>'razon_social', nullif(d->>'fecha', '')::date, nullif(d->>'total', '')::numeric, p_archivo,
         v_usuario, now(),
         case when p_estado = 'importada' then v_usuario end,
         case when p_estado = 'importada' then now() end
  from jsonb_array_elements(p_documentos) d
  where coalesce(d->>'rut', '') <> '' and coalesce(d->>'docto', '') <> '' and coalesce(d->>'folio', '') <> ''
  on conflict (empresa, rut, docto, folio) do update set
    estado        = case when ci.estado = 'importada' then 'importada' else excluded.estado end,
    razon_social  = coalesce(excluded.razon_social, ci.razon_social),
    fecha_doc     = coalesce(excluded.fecha_doc, ci.fecha_doc),
    total         = coalesce(excluded.total, ci.total),
    archivo       = coalesce(excluded.archivo, ci.archivo),
    preparado_por = case when excluded.estado = 'preparada' then excluded.preparado_por else ci.preparado_por end,
    preparado_en  = case when excluded.estado = 'preparada' then excluded.preparado_en  else ci.preparado_en  end,
    importado_por = case when excluded.estado = 'importada' then excluded.importado_por else ci.importado_por end,
    importado_en  = case when excluded.estado = 'importada' then excluded.importado_en  else ci.importado_en  end;
  get diagnostics v_n = row_count;
  return v_n;
end $$;

-- Quita la marca (por ejemplo si se preparó por error o Manager la rechazó).
create or replace function public.desmarcar_compra_manager(p_empresa text, p_rut text, p_docto text, p_folio bigint)
returns void language plpgsql security definer set search_path = shg_dashboards, public as $$
begin
  if public.puede_ver('finanzas') is null then
    raise exception 'Sin acceso a Finanzas';
  end if;
  delete from shg_dashboards.compras_importacion
   where empresa = coalesce(p_empresa, 'polchile') and rut = upper(replace(trim(p_rut), '.', ''))
     and docto = p_docto and folio = p_folio;
end $$;

revoke all on function public.marcar_compras_manager(text, text, jsonb, text) from public, anon;
revoke all on function public.desmarcar_compra_manager(text, text, text, bigint) from public, anon;
grant execute on function public.marcar_compras_manager(text, text, jsonb, text) to authenticated;
grant execute on function public.desmarcar_compra_manager(text, text, text, bigint) to authenticated;

-- Estado combinado: lo que dice Manager (copia diaria) gana sobre la marca manual.
create or replace view shg_dashboards.compras_estado_manager with (security_invoker = true) as
select ci.empresa, ci.rut, ci.docto, ci.folio, ci.razon_social, ci.fecha_doc, ci.total,
       case when md.num_docto is not null then 'en_manager' else ci.estado end as estado,
       ci.archivo, ci.preparado_por, ci.preparado_en, ci.importado_por, ci.importado_en,
       md.fecha as fecha_en_manager
from shg_dashboards.compras_importacion ci
left join shg_dashboards.compras_manager_docs md
       on md.docto = ci.docto and md.rut = ci.rut and md.num_docto = ci.folio and coalesce(md.nula, 0) = 0;
revoke all on shg_dashboards.compras_estado_manager from anon;
grant select on shg_dashboards.compras_estado_manager to authenticated;

-- Comprobación
-- select estado, count(*) from shg_dashboards.compras_estado_manager group by estado;
