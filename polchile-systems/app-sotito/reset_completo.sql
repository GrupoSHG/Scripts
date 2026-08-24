-- ============================================================
-- RESET COMPLETO — borra y recrea todo desde cero
-- Correr en el SQL Editor del proyecto ffxopvzxyeacpbtxuagu
-- ============================================================

-- 1. Borrar todo lo existente (en orden por las foreign keys)
drop trigger if exists trg_asistencia_facturacion on asistencia;
drop trigger if exists trg_gastos_facturacion on gastos;
drop function if exists fn_trigger_asistencia_facturacion();
drop function if exists fn_trigger_gastos_facturacion();
drop function if exists fn_recalcular_facturacion(uuid, date);

drop table if exists facturacion cascade;
drop table if exists gastos cascade;
drop table if exists facturas cascade;
drop table if exists asistencia cascade;
drop table if exists iniciativas cascade;
drop table if exists personas cascade;
drop table if exists centros_costo cascade;

-- 2. Recrear tablas
create table centros_costo (
  id uuid primary key default gen_random_uuid(),
  codigo text unique not null,
  nombre text not null,
  responsable text,
  factura_a text,
  presupuesto_mensual numeric,
  activo boolean default true,
  created_at timestamptz default now()
);

create table personas (
  id uuid primary key default gen_random_uuid(),
  nombre text not null,
  cargo text,
  tarifa_diaria numeric,
  activo boolean default true
);

create table iniciativas (
  id uuid primary key default gen_random_uuid(),
  centro_costo_id uuid references centros_costo(id),
  nombre text not null,
  descripcion text,
  estado text check (estado in ('planificada','en_curso','completada')),
  fecha_inicio date,
  fecha_fin date
);

create table asistencia (
  id uuid primary key default gen_random_uuid(),
  centro_costo_id uuid references centros_costo(id),
  persona_id uuid references personas(id),
  fecha date not null,
  presente boolean default true,
  unique(centro_costo_id, persona_id, fecha)
);

create table facturas (
  id uuid primary key default gen_random_uuid(),
  centro_costo_id uuid references centros_costo(id),
  foto_url text not null,
  proveedor text,
  monto numeric,
  fecha date,
  estado_ocr text check (estado_ocr in ('pendiente','leida','confirmada','error')),
  created_at timestamptz default now()
);

create table gastos (
  id uuid primary key default gen_random_uuid(),
  centro_costo_id uuid references centros_costo(id),
  fecha date not null,
  descripcion text,
  monto numeric not null,
  categoria text,
  factura_id uuid references facturas(id),
  created_by text,
  created_at timestamptz default now()
);

create table facturacion (
  id uuid primary key default gen_random_uuid(),
  centro_costo_id uuid references centros_costo(id),
  mes date not null,
  mano_obra numeric not null default 0,
  gastos_netos numeric not null default 0,
  leyes_sociales_pct numeric not null default 0.30,
  utilidad_pct numeric not null default 0.05,
  iva_pct numeric not null default 0.19,
  subtotal numeric generated always as (mano_obra * (1 + leyes_sociales_pct) + gastos_netos) stored,
  neto numeric generated always as ((mano_obra * (1 + leyes_sociales_pct) + gastos_netos) * (1 + utilidad_pct)) stored,
  iva numeric generated always as ((mano_obra * (1 + leyes_sociales_pct) + gastos_netos) * (1 + utilidad_pct) * iva_pct) stored,
  total numeric generated always as ((mano_obra * (1 + leyes_sociales_pct) + gastos_netos) * (1 + utilidad_pct) * (1 + iva_pct)) stored,
  unique(centro_costo_id, mes)
);

-- 3. Datos maestros de CyS
insert into centros_costo (codigo, nombre, factura_a, activo) values
  ('CYS-BUIN',     'Buin',            'Sergio Reyes',    true),
  ('CYS-ELTABO',   'El Tabo',         'Jefe Starken',    true),
  ('CYS-JARDIN',   'Jardín',          'Jardín',          true),
  ('CYS-CODEGUA',  'Codegua',         'Rafael Diez',     true),
  ('CYS-POLCHILE', 'Polchile',        'Polchile',        true),
  ('CYS-LOSPALTOS','Los Paltos (LP)', 'Polchile',        true),
  ('CYS-STARKEN',  'Starken',         'EXCLUIDA',        true);

insert into personas (nombre, tarifa_diaria, activo) values
  ('Ivan Soto',              45000, true),
  ('Alfonso Lauquen',        41000, true),
  ('Francisco Lauquen',      41000, true),
  ('Byron Silva',            33500, true),
  ('Sebastian Lauquen',      30000, true),
  ('Demian Concha',          30000, true),
  ('Ricardo Chacon',         32500, true);

-- 4. RLS + políticas
alter table centros_costo enable row level security;
create policy "Lectura pública" on centros_costo for select using (true);

alter table personas enable row level security;
create policy "Lectura pública" on personas for select using (true);
create policy "Escritura pública" on personas for insert with check (true);

alter table asistencia enable row level security;
create policy "Lectura pública" on asistencia for select using (true);
create policy "Escritura pública" on asistencia for all using (true) with check (true);

alter table gastos enable row level security;
create policy "Lectura pública" on gastos for select using (true);
create policy "Escritura pública" on gastos for all using (true) with check (true);

alter table facturacion enable row level security;
create policy "Lectura pública" on facturacion for select using (true);

alter table facturas enable row level security;
create policy "Lectura pública" on facturas for select using (true);
create policy "Escritura pública" on facturas for all using (true) with check (true);

alter table iniciativas enable row level security;
create policy "Lectura pública" on iniciativas for select using (true);

-- 5. Grants explícitos
grant usage on schema public to anon, authenticated;
grant select on centros_costo to anon, authenticated;
grant select, insert on personas to anon, authenticated;
grant select, insert, update on asistencia to anon, authenticated;
grant select, insert, update on gastos to anon, authenticated;
grant select on facturacion to anon, authenticated;
grant select, insert, update on facturas to anon, authenticated;
grant select on iniciativas to anon, authenticated;

-- 6. Función y triggers de recálculo automático de facturación
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

create trigger trg_asistencia_facturacion
after insert or update or delete on asistencia
for each row execute function fn_trigger_asistencia_facturacion();

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

create trigger trg_gastos_facturacion
after insert or update or delete on gastos
for each row execute function fn_trigger_gastos_facturacion();

-- 7. Verificación final
select 'centros_costo' as tabla, count(*) as filas from centros_costo
union all
select 'personas', count(*) from personas;
