-- App Sotito — esquema Supabase (Postgres)

create table centros_costo (
  id uuid primary key default gen_random_uuid(),
  codigo text unique not null,
  nombre text not null,
  responsable text,
  factura_a text,              -- a quién se factura este centro (persona/empresa). NULL o 'EXCLUIDA' si no aplica
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

-- Facturación mensual por centro de costo, calculada con la fórmula intercompany:
-- (Mano de obra x (1 + leyes_sociales_pct) + Gastos netos) x (1 + utilidad_pct) = Neto
-- Neto x iva_pct = IVA · Neto + IVA = Total
create table facturacion (
  id uuid primary key default gen_random_uuid(),
  centro_costo_id uuid references centros_costo(id),
  mes date not null,                          -- primer día del mes, ej. 2026-07-01
  mano_obra numeric not null default 0,       -- suma de tarifa_diaria x jornadas del mes
  gastos_netos numeric not null default 0,    -- suma de gastos del centro de costo en el mes (sin IVA)
  leyes_sociales_pct numeric not null default 0.30,
  utilidad_pct numeric not null default 0.05,
  iva_pct numeric not null default 0.19,
  subtotal numeric generated always as (mano_obra * (1 + leyes_sociales_pct) + gastos_netos) stored,
  neto numeric generated always as ((mano_obra * (1 + leyes_sociales_pct) + gastos_netos) * (1 + utilidad_pct)) stored,
  iva numeric generated always as ((mano_obra * (1 + leyes_sociales_pct) + gastos_netos) * (1 + utilidad_pct) * iva_pct) stored,
  total numeric generated always as ((mano_obra * (1 + leyes_sociales_pct) + gastos_netos) * (1 + utilidad_pct) * (1 + iva_pct)) stored,
  unique(centro_costo_id, mes)
);

-- Nota: la mano de obra por centro de costo y mes se calcula sumando
-- personas.tarifa_diaria x días donde asistencia.presente = true,
-- agrupado por centro_costo_id y mes (no se necesita tabla aparte).

-- Bucket de Storage para las fotos de factura (crear desde el dashboard o CLI):
-- supabase storage buckets create facturas --public
