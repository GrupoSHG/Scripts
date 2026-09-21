-- =====================================================
-- OC POLCHILE - Schema Supabase
-- Ejecutar en SQL Editor de tu proyecto Supabase
-- =====================================================

-- Usuarios (login por PIN)
create table usuarios (
  id uuid primary key default gen_random_uuid(),
  nombre text not null,
  pin text not null unique,
  rol text not null default 'user', -- 'admin' | 'user'
  activo boolean not null default true,
  created_at timestamptz not null default now()
);

-- Proveedores (se auto-crean en marcha blanca)
create table proveedores (
  id uuid primary key default gen_random_uuid(),
  nombre text not null,
  rut text,
  direccion text,
  ciudad text,
  comuna text, -- state/province
  codigo_postal text,
  pais text default 'Chile',
  contacto text,
  telefono text,
  email text,
  created_at timestamptz not null default now(),
  created_by uuid references usuarios(id)
);
create index idx_proveedores_nombre on proveedores using gin (to_tsvector('spanish', nombre));

-- Contactos por proveedor (ej: "Despacho Motos", "Despacho Camión")
create table proveedor_contactos (
  id uuid primary key default gen_random_uuid(),
  proveedor_id uuid not null references proveedores(id) on delete cascade,
  nombre text not null,
  created_at timestamptz not null default now()
);
create index idx_proveedor_contactos_prov on proveedor_contactos(proveedor_id);

-- Notas de Venta (NV) - referencia para medir % de costo
create table nvs (
  id uuid primary key default gen_random_uuid(),
  numero text not null unique, -- ej NV 13804
  cliente text,
  descripcion text,
  monto_neto numeric(14,2) not null default 0,
  umbral_pct numeric(5,2) not null default 65.00, -- % variable por NV
  categoria text, -- para umbral por categoría si se prefiere
  estado text not null default 'abierta', -- 'abierta' | 'cerrada'
  created_at timestamptz not null default now(),
  created_by uuid references usuarios(id)
);

-- Categorías con umbral por defecto (opcional, para no repetir manualmente)
create table categorias_umbral (
  id uuid primary key default gen_random_uuid(),
  nombre text not null unique,
  umbral_pct numeric(5,2) not null default 65.00
);

-- Órdenes de Compra (cabecera)
create table ocs (
  id uuid primary key default gen_random_uuid(),
  numero text not null unique, -- correlativo autogenerado, ej OC-0001
  nv_id uuid not null references nvs(id) on delete restrict,
  proveedor_id uuid not null references proveedores(id) on delete restrict,
  contacto_id uuid references proveedor_contactos(id),
  contacto_nombre text, -- copia del nombre al momento de crear la OC
  location text default 'POLCHILE',
  drop_ship boolean default true,
  ship_name text,
  ship_address1 text,
  ship_address2 text,
  ship_city text,
  ship_state text,
  ship_postal_code text,
  ship_country text default 'Chile',
  descripcion text,
  notas text,
  fecha_llegada date,
  freight numeric(14,2) default 0,
  total numeric(14,2) not null default 0, -- suma de items + freight
  estado text not null default 'pendiente', -- 'pendiente' | 'autorizada' | 'revocada'
  created_at timestamptz not null default now(),
  created_by uuid references usuarios(id),
  authorized_at timestamptz,
  authorized_by uuid references usuarios(id)
);
create index idx_ocs_nv on ocs(nv_id);
create index idx_ocs_estado on ocs(estado);

-- Items de cada OC
create table oc_items (
  id uuid primary key default gen_random_uuid(),
  oc_id uuid not null references ocs(id) on delete cascade,
  vendor_part_number text,
  descripcion text not null,
  qty numeric(12,2) not null default 1,
  rate numeric(14,2) not null default 0,
  amount numeric(14,2) generated always as (qty * rate) stored,
  cogs_account text default 'In-House Material Expense',
  orden int default 0
);
create index idx_oc_items_oc on oc_items(oc_id);

-- =====================================================
-- Trigger: recalcular total de la OC cuando cambian items
-- =====================================================
create or replace function recalcular_total_oc()
returns trigger as $$
declare
  v_oc_id uuid;
begin
  v_oc_id := coalesce(new.oc_id, old.oc_id);
  update ocs
  set total = (
    select coalesce(sum(amount),0) from oc_items where oc_id = v_oc_id
  ) + coalesce((select freight from ocs where id = v_oc_id),0)
  where id = v_oc_id;
  return null;
end;
$$ language plpgsql;

create trigger trg_recalcular_total_oc
after insert or update or delete on oc_items
for each row execute function recalcular_total_oc();

-- =====================================================
-- Vista: control de autorización (equivalente a imagen 3)
-- =====================================================
create view v_control_autorizacion as
select
  n.id as nv_id,
  n.numero as nv_numero,
  n.cliente,
  n.monto_neto as nv_monto_neto,
  n.umbral_pct,
  coalesce(sum(o.total),0) as suma_ocs,
  case when n.monto_neto > 0
    then round((coalesce(sum(o.total),0) / n.monto_neto) * 100, 1)
    else 0
  end as pct_consumido,
  count(o.id) as cantidad_ocs,
  count(o.id) filter (where o.estado = 'autorizada') as ocs_autorizadas,
  bool_and(o.estado = 'autorizada') filter (where o.id is not null) as todas_autorizadas
from nvs n
left join ocs o on o.nv_id = n.id
group by n.id, n.numero, n.cliente, n.monto_neto, n.umbral_pct;

-- =====================================================
-- Correlativo de OC (OC-0001, OC-0002...)
-- =====================================================
create sequence oc_correlativo start 1;

create or replace function generar_numero_oc()
returns trigger as $$
begin
  if new.numero is null then
    new.numero := 'OC-' || lpad(nextval('oc_correlativo')::text, 5, '0');
  end if;
  return new;
end;
$$ language plpgsql;

create trigger trg_generar_numero_oc
before insert on ocs
for each row execute function generar_numero_oc();

-- =====================================================
-- RLS (ajustar según cómo se maneje el PIN — ver nota abajo)
-- =====================================================
alter table usuarios enable row level security;
alter table proveedores enable row level security;
alter table proveedor_contactos enable row level security;
alter table nvs enable row level security;
alter table ocs enable row level security;
alter table oc_items enable row level security;
alter table categorias_umbral enable row level security;

-- Con auth anónima de Supabase + PIN validado en la app (no en RLS por rol de DB),
-- se abre acceso a anon y se controla el permiso de "aprobar" en el frontend
-- (igual patrón que Despachos Polchile con Firebase Anonymous Auth).
create policy "anon full access" on usuarios for all using (true) with check (true);
create policy "anon full access" on proveedores for all using (true) with check (true);
create policy "anon full access" on proveedor_contactos for all using (true) with check (true);
create policy "anon full access" on nvs for all using (true) with check (true);
create policy "anon full access" on ocs for all using (true) with check (true);
create policy "anon full access" on oc_items for all using (true) with check (true);
create policy "anon full access" on categorias_umbral for all using (true) with check (true);

-- Usuario admin de ejemplo (cambiar PIN real)
insert into usuarios (nombre, pin, rol) values ('Gonzalo Alcayaga', '1234', 'admin');
