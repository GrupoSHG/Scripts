-- Facturas recibidas por correo (XML de DTE) para la pantalla RCV del Dashboard Finanzas.
-- Las llena el workflow dte-correo-sync.yml (Polchile_Systems/sync_dte_correo.py) leyendo
-- la casilla dte@polchile.cl. Se aplica a mano en el SQL Editor de Supabase; es idempotente.
--
-- Lectura: la Edge Function rcv-sii (service_role) y los usuarios autenticados de los
-- dashboards (solo lectura). Escritura: solo service_role (el workflow).

create table if not exists shg_dashboards.dte_recibidos (
  id                    bigint generated always as identity primary key,
  rut_emisor            text        not null,      -- 76123456-7
  tipo_dte              int         not null,      -- 33 factura, 34 exenta, 61 nota de crédito, 56 débito, 52 guía...
  folio                 bigint      not null,
  fecha_emision         date,
  fecha_vencimiento     date,
  forma_pago            text,
  razon_social_emisor   text,
  giro_emisor           text,
  rut_receptor          text,                      -- empresa del grupo que recibe (Polchile, M5...)
  razon_social_receptor text,
  monto_neto            numeric,
  monto_exento          numeric,
  iva                   numeric,
  monto_total           numeric,
  items                 jsonb       not null default '[]'::jsonb,  -- Detalle del DTE (descripcion, cantidad, precioUnitario, monto...)
  referencias           jsonb       not null default '[]'::jsonb,  -- Referencia (OC, guías, facturas anuladas...)
  xml                   text        not null,      -- el elemento DTE completo, con firma
  archivo               text,                      -- nombre del adjunto (o zip/entrada)
  correo_uid            bigint,
  correo_asunto         text,
  correo_de             text,
  correo_fecha          timestamptz,
  recibido_en           timestamptz not null default now(),
  unique (rut_emisor, tipo_dte, folio)
);
create index if not exists dte_recibidos_folio_idx on shg_dashboards.dte_recibidos (folio);
create index if not exists dte_recibidos_receptor_fecha_idx on shg_dashboards.dte_recibidos (rut_receptor, fecha_emision desc);

-- Cursor de lectura de la casilla: último UID IMAP procesado (uno por buzón).
create table if not exists shg_dashboards.dte_correo_cursor (
  buzon          text        primary key,
  ultimo_uid     bigint      not null default 0,
  uidvalidity    bigint,
  ultimos_nuevos int         not null default 0,  -- correos con XML en la última pasada
  actualizado_en timestamptz not null default now()
);

alter table shg_dashboards.dte_recibidos    enable row level security;
alter table shg_dashboards.dte_correo_cursor enable row level security;

drop policy if exists dte_recibidos_lectura on shg_dashboards.dte_recibidos;
create policy dte_recibidos_lectura on shg_dashboards.dte_recibidos
  for select to authenticated using (true);
drop policy if exists dte_correo_cursor_lectura on shg_dashboards.dte_correo_cursor;
create policy dte_correo_cursor_lectura on shg_dashboards.dte_correo_cursor
  for select to authenticated using (true);

revoke all on shg_dashboards.dte_recibidos, shg_dashboards.dte_correo_cursor from anon;
grant select on shg_dashboards.dte_recibidos, shg_dashboards.dte_correo_cursor to authenticated;
grant all on shg_dashboards.dte_recibidos, shg_dashboards.dte_correo_cursor to service_role;

-- Botón "Actualizar datos" y fecha del último dato (ver automatizacion/actualizar_datos_manual.sql).
insert into automatizacion.workflows_manual (workflow, nombre, inputs, espera_min, duracion_min) values
  ('dte-correo-sync.yml', 'Facturas recibidas por correo (XML DTE)', '{}', 5, 3)
on conflict (workflow) do update set nombre = excluded.nombre, inputs = excluded.inputs,
  espera_min = excluded.espera_min, duracion_min = excluded.duracion_min;
