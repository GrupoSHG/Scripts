-- Fichas de postulación de licitaciones M5: requisitos, garantías, criterios, contrato, riesgos, checklist y
-- recomendación extraídos con Claude de las bases (PDF del bucket licitaciones-bases). Una fila por licitación,
-- se reemplaza cuando cambian los PDF. La llena M5_Systems/licitaciones-m5 (fichas.py, dentro del comando
-- `diario`) con el rol licitaciones_m5. Se aplica a mano; es idempotente.
-- Requiere licitaciones_mp_evaluacion.sql (rol licitaciones_m5) y bases_costos.sql (m5.licitaciones_bases).
-- Va en Supabase y no en el artefacto de Actions porque el repo Scripts es público.

create table if not exists m5.licitaciones_fichas (
  codigo_externo      text primary key,
  estado              text not null
                      check (estado in ('lista', 'revision_manual', 'adjuntos_pendientes', 'escaneado', 'error')),
  recomendacion       text check (recomendacion in ('postular', 'revisar', 'descartar')),
  razones             text[] not null default '{}',
  fecha_cierre        timestamptz,
  dias_habiles_cierre int,                  -- al generar la ficha (calculado por el código)
  alerta_cierre       boolean not null default false,
  bases_ids           bigint[] not null default '{}',   -- PDF de m5.licitaciones_bases usados; si cambian, se rehace
  ficha               jsonb not null,       -- ficha completa: datos, extracción con página y cita, cálculos, checklist
  ficha_md            text not null,        -- la misma ficha en Markdown
  modelo              text,
  tokens              jsonb,
  costo_usd           numeric,
  error               text,
  generado_en         timestamptz not null default now()
);
create index if not exists licitaciones_fichas_cierre_idx on m5.licitaciones_fichas (fecha_cierre);

comment on table m5.licitaciones_fichas is
  'Fichas de postulación extraídas automáticamente de las bases: confirmar montos, plazos y garantías con las bases originales. Fuente: Scripts/M5_Systems/licitaciones-m5 (fichas.py).';

-- Acceso: el equipo con sesión lee (no los clientes externos de M5); el proceso lee y hace upsert.
alter table m5.licitaciones_fichas enable row level security;
revoke all on m5.licitaciones_fichas from anon, public;
grant select on m5.licitaciones_fichas to authenticated;
grant select, insert, update on m5.licitaciones_fichas to licitaciones_m5;

drop policy if exists lectura_autenticados on m5.licitaciones_fichas;
create policy lectura_autenticados on m5.licitaciones_fichas for select to authenticated using (true);
drop policy if exists proceso_licitaciones_m5 on m5.licitaciones_fichas;
create policy proceso_licitaciones_m5 on m5.licitaciones_fichas for all to licitaciones_m5 using (true) with check (true);
drop policy if exists sin_clientes_externos on m5.licitaciones_fichas;
create policy sin_clientes_externos on m5.licitaciones_fichas as restrictive for all to authenticated
  using (coalesce(shg_dashboards.rol_actual(), '') <> 'cliente');

select count(*) as fichas from m5.licitaciones_fichas;
