-- App Sotito — esquema Supabase (Postgres)

create table centros_costo (
  id uuid primary key default gen_random_uuid(),
  codigo text unique not null,
  nombre text not null,
  responsable text,
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
  fecha date not null,
  monto numeric not null,
  tipo text check (tipo in ('estimada','real')),
  referencia text
);

-- Bucket de Storage para las fotos de factura (crear desde el dashboard o CLI):
-- supabase storage buckets create facturas --public
