-- Plan de cuentas contables y calce código de artículo → cuenta, para la pantalla
-- RCV · SII del Dashboard Finanzas (carga de detalle de facturas a Manager).
-- Se aplica a mano en el SQL Editor de Supabase; es idempotente.
--
-- plan_cuentas   : el plan de cuentas de cada empresa (lo carga cargar_plan_cuentas.py
--                  desde el Excel/CSV exportado de Manager).
-- codigos_cuenta : qué cuenta contable corresponde a cada código de artículo. Se carga
--                  desde el export "artículos y cuentas" de Manager (cargar_codigos_cuenta.py:
--                  6.641 artículos en oct-2026) y lo sigue llenando la pantalla cada vez que
--                  finanzas completa código + cuenta en el detalle de una factura (ruta
--                  POST /cuenta-contable de rcv-sii), así la próxima factura se autocompleta.
--
-- Lectura: usuarios autenticados de los dashboards y la Edge Function rcv-sii.
-- Escritura: solo service_role (el cargador y la Edge Function).

create table if not exists shg_dashboards.plan_cuentas (
  empresa        text    not null default 'polchile',   -- polchile | m5
  codigo         text    not null,                      -- código de la cuenta tal como lo usa Manager
  nombre         text    not null,
  tipo           text,                                  -- Activo, Pasivo, Patrimonio, Resultado... (si el plan lo trae)
  nivel          int,                                   -- profundidad en el árbol (si el plan lo trae)
  imputable      boolean not null default true,         -- false = cuenta de agrupación, no se usa en asientos
  activo         boolean not null default true,
  actualizado_en timestamptz not null default now(),
  primary key (empresa, codigo)
);
create index if not exists plan_cuentas_nombre_idx on shg_dashboards.plan_cuentas (empresa, lower(nombre));

create table if not exists shg_dashboards.codigos_cuenta (
  empresa         text    not null default 'polchile',
  codigo_item     text    not null,                     -- código de artículo / ítem que digita finanzas
  cuenta          text    not null,                     -- cuenta contable de COMPRA (la que usa el detalle de facturas)
  cuenta_venta    text,                                 -- cuenta de venta del artículo (export de Manager)
  cuenta_costo    text,                                 -- cuenta de costo del artículo (export de Manager)
  descripcion     text,                                 -- última descripción vista para ese código (referencia)
  actualizado_por text,                                 -- email del usuario que lo asignó, o 'manager-export'
  actualizado_en  timestamptz not null default now(),
  primary key (empresa, codigo_item)
);

alter table shg_dashboards.plan_cuentas   enable row level security;
alter table shg_dashboards.codigos_cuenta enable row level security;

drop policy if exists plan_cuentas_lectura on shg_dashboards.plan_cuentas;
create policy plan_cuentas_lectura on shg_dashboards.plan_cuentas
  for select to authenticated using (true);
drop policy if exists codigos_cuenta_lectura on shg_dashboards.codigos_cuenta;
create policy codigos_cuenta_lectura on shg_dashboards.codigos_cuenta
  for select to authenticated using (true);

revoke all on shg_dashboards.plan_cuentas, shg_dashboards.codigos_cuenta from anon;
grant select on shg_dashboards.plan_cuentas, shg_dashboards.codigos_cuenta to authenticated;
grant all on shg_dashboards.plan_cuentas, shg_dashboards.codigos_cuenta to service_role;
