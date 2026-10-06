-- =====================================================================
-- facturas_sin_nv.sql  (se aplica a mano en el SQL Editor de Supabase)
-- Proyecto ffxopvzxyeacpbtxuagu, esquema shg_dashboards. Idempotente.
--
-- Acompaña a backup-manager/ConsultasSQL/Facturas_Manager.sql (pipeline diario):
-- trae TODAS las facturas, boletas, notas de débito y de crédito de venta
-- desde 2025 (una fila por documento), incluidas las que el Ventas Full
-- deja fuera (líneas con el artículo genérico "-") y las que no
-- referencian ninguna Nota de Venta.
--
-- Problema que resuelve: hay facturas emitidas sin NV (sin NROPEDIDO ni
-- guía de origen), así que la NV del cliente sigue apareciendo con saldo
-- pendiente en Trazabilidad NV aunque ya se facturó. Ahora:
--   1. shg_dashboards.facturas_manager            tabla espejo (la llena el pipeline).
--   2. shg_dashboards.facturas_nv_manual  asociación factura -> NV hecha a
--      mano desde la app Trazabilidad NV (RPC asignar_factura_nv).
--   3. trazabilidad_nv / trazabilidad_nv_documentos  suman también las
--      asociaciones manuales y los documentos que solo están en facturas.
--   4. trazabilidad_facturas_sin_nv       lista de facturas sin NV con las NV
--      del mismo RUT que aún tienen saldo pendiente (candidatas).
--   5. trazabilidad_nv_auto              asociación automática: factura sin NV ->
--      NV de la factura anterior del mismo RUT (correlativo, <= 30 días) con saldo.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Tabla facturas_manager. Mismas columnas, orden y tipos que infiere
--    bulk_sync_supabase.py desde Facturas_Manager.sql: así el pipeline la vacía con
--    TRUNCATE + COPY y no intenta recrearla (un DROP fallaría por las vistas).
--    nota_venta / factura_ref / numguiaf van bigint (ajustar_enteros los
--    convierte desde float).
-- ---------------------------------------------------------------------
create table if not exists shg_dashboards.facturas_manager (
    docto             text,
    num_docto         bigint,
    numreg            bigint,
    fecha             timestamp,
    fecha_vencimiento timestamp,
    nula              bigint,
    rut               text,
    cliente           text,
    cod_vddor         text,
    vendedor          text,
    total_neto        double precision,
    total_iva         double precision,
    total             double precision,
    nropedido         text,
    nota_venta        bigint,
    origen_nv         text,
    factura_ref       bigint,
    numguiaf          bigint,
    n_lineas          bigint,
    glosa             text
);
alter table shg_dashboards.facturas_manager enable row level security;
drop policy if exists lectura_publica_facturas_manager on shg_dashboards.facturas_manager;
create policy lectura_publica_facturas_manager on shg_dashboards.facturas_manager for select to authenticated using (true);
revoke all on shg_dashboards.facturas_manager from anon;
grant select on shg_dashboards.facturas_manager to authenticated, service_role;
create index if not exists facturas_manager_docto_num_idx on shg_dashboards.facturas_manager (docto, num_docto);
create index if not exists facturas_manager_nota_venta_idx on shg_dashboards.facturas_manager (nota_venta);

-- ---------------------------------------------------------------------
-- 2. Asociaciones manuales factura -> NV (desde la app Trazabilidad NV).
-- ---------------------------------------------------------------------
create table if not exists shg_dashboards.facturas_nv_manual (
    docto        text        not null default 'FAV',
    num_docto    bigint      not null,
    nota_venta   bigint      not null,
    asignado_por text,
    asignado_en  timestamptz not null default now(),
    primary key (docto, num_docto)
);
alter table shg_dashboards.facturas_nv_manual enable row level security;
drop policy if exists lectura_facturas_nv_manual on shg_dashboards.facturas_nv_manual;
create policy lectura_facturas_nv_manual on shg_dashboards.facturas_nv_manual for select to authenticated using (true);
revoke all on shg_dashboards.facturas_nv_manual from anon, authenticated;
grant select on shg_dashboards.facturas_nv_manual to authenticated, service_role;

-- Solo roles con nivel >= 50 (admin, director, jefatura) pueden asociar o
-- quitar. Las RPC corren como security definer; escriben el correo del usuario.
create or replace function shg_dashboards.puede_asociar_facturas()
returns boolean language sql stable security definer set search_path = shg_dashboards, public as $$
  select coalesce((select r.nivel >= 50 from shg_dashboards.roles r where r.rol = shg_dashboards.rol_actual()), false)
$$;
revoke all on function shg_dashboards.puede_asociar_facturas() from public, anon;
grant execute on function shg_dashboards.puede_asociar_facturas() to authenticated;

create or replace function public.asignar_factura_nv(p_docto text, p_num_docto bigint, p_nota_venta bigint)
returns text language plpgsql security definer set search_path = shg_dashboards, public as $$
declare v_email text; v_existe boolean;
begin
  if auth.uid() is null then return 'ERROR: sin sesión'; end if;
  if not shg_dashboards.puede_asociar_facturas() then return 'ERROR: tu rol no puede asociar facturas'; end if;
  if p_docto not in ('FAV', 'BOV', 'NDV', 'NCV') then return 'ERROR: tipo de documento inválido'; end if;
  if p_nota_venta is null or p_nota_venta <= 0 then return 'ERROR: N° de NV inválido'; end if;

  select exists (select 1 from shg_dashboards.ventas_full v where v.docto = p_docto and v.num_docto = p_num_docto)
      or exists (select 1 from shg_dashboards.facturas_manager f where f.docto = p_docto and f.num_docto = p_num_docto)
    into v_existe;
  if not v_existe then return 'ERROR: el documento ' || p_docto || ' ' || p_num_docto || ' no existe en Manager'; end if;

  if not exists (select 1 from shg_dashboards.notas_de_venta nv where nv.numnota = p_nota_venta) then
    return 'ERROR: la NV ' || p_nota_venta || ' no está en la tabla de Notas de Venta';
  end if;

  v_email := coalesce(auth.jwt() ->> 'email', auth.uid()::text);
  insert into shg_dashboards.facturas_nv_manual (docto, num_docto, nota_venta, asignado_por, asignado_en)
  values (p_docto, p_num_docto, p_nota_venta, v_email, now())
  on conflict (docto, num_docto) do update
    set nota_venta = excluded.nota_venta, asignado_por = excluded.asignado_por, asignado_en = now();
  return 'OK';
end $$;

create or replace function public.quitar_factura_nv(p_docto text, p_num_docto bigint)
returns text language plpgsql security definer set search_path = shg_dashboards, public as $$
begin
  if auth.uid() is null then return 'ERROR: sin sesión'; end if;
  if not shg_dashboards.puede_asociar_facturas() then return 'ERROR: tu rol no puede asociar facturas'; end if;
  delete from shg_dashboards.facturas_nv_manual where docto = p_docto and num_docto = p_num_docto;
  return 'OK';
end $$;

revoke all on function public.asignar_factura_nv(text, bigint, bigint) from public, anon;
grant execute on function public.asignar_factura_nv(text, bigint, bigint) to authenticated;
revoke all on function public.quitar_factura_nv(text, bigint) from public, anon;
grant execute on function public.quitar_factura_nv(text, bigint) to authenticated;
-- ---------------------------------------------------------------------
-- 3. Vistas de trazabilidad. La NV de cada documento es la del Ventas Full
--    o, si no tiene, la asociación manual o la automática. Los documentos
--    que solo están en facturas_manager (artículo genérico "-") entran con su
--    total neto de cabecera, solo los del año en curso (mismo alcance que el
--    Ventas Full; la tabla guarda desde 2025 y sin este filtro aparecían
--    ~730 NV de 2025 como "Sin NV en Manager").
--
--    Asociación automática (trazabilidad_nv_auto): una factura sin NV se
--    asigna a la NV de la factura anterior del mismo RUT (número menor más
--    cercano, emitida hasta 30 días antes) mientras esa NV tenga saldo
--    pendiente sin contar las automáticas. La manual tiene prioridad.
--    Verificado el 05-oct-2026: las 6 facturas de Agrícola Los del Monte
--    cuadran las NV 14022 y 14090, y la 19117 la NV 13211.
--
--    Orden de dependencia:
--      trazabilidad_nv_documentos_base    docs con NV (Ventas Full, manual, facturas_manager)
--      trazabilidad_facturas_sin_nv_base  docs sin NV (Ventas Full + facturas_manager)
--      trazabilidad_nv_auto               regla automática
--      trazabilidad_nv_documentos         base + automáticas (+ asignacion_manual / asignacion_auto)
--      trazabilidad_nv                    mismas columnas de siempre + n_facturas_manual, n_facturas_auto
--      trazabilidad_facturas_sin_nv       base sin NV + manual + auto + NV candidatas por RUT
-- ---------------------------------------------------------------------
create or replace view shg_dashboards.trazabilidad_nv_documentos_base as
with vf as (
    select
        coalesce(v.nota_venta, m.nota_venta)                         as nota_venta,
        v.docto,
        v.num_docto,
        min(v.fecha_emision)::date                                   as fecha,
        max(v.cliente)                                               as cliente,
        round(sum(coalesce(v.total_neto, 0)))::bigint                as total_neto,
        max(v.factura_ref)                                           as factura_ref,
        count(*)                                                     as n_lineas,
        bool_or(v.nota_venta is null and m.nota_venta is not null)   as asignacion_manual
    from shg_dashboards.ventas_full v
    left join shg_dashboards.facturas_nv_manual m on m.docto = v.docto and m.num_docto = v.num_docto
    where coalesce(v.nota_venta, m.nota_venta) is not null
    group by coalesce(v.nota_venta, m.nota_venta), v.docto, v.num_docto
),
solo_facturas as (
    select
        coalesce(f.nota_venta, m.nota_venta)                         as nota_venta,
        f.docto,
        f.num_docto,
        f.fecha::date                                                as fecha,
        f.cliente,
        round(coalesce(f.total_neto, 0))::bigint                     as total_neto,
        f.factura_ref,
        coalesce(f.n_lineas, 0)                                      as n_lineas,
        (f.nota_venta is null and m.nota_venta is not null)          as asignacion_manual
    from shg_dashboards.facturas_manager f
    left join shg_dashboards.facturas_nv_manual m on m.docto = f.docto and m.num_docto = f.num_docto
    where coalesce(f.nota_venta, m.nota_venta) is not null
      and coalesce(f.nula, 0) = 0
      and f.docto in ('FAV', 'BOV', 'NDV', 'NCV')
      and f.fecha >= date_trunc('year', current_date)
      and not exists (select 1 from shg_dashboards.ventas_full v where v.docto = f.docto and v.num_docto = f.num_docto)
)
select * from vf
union all
select * from solo_facturas;

create or replace view shg_dashboards.trazabilidad_facturas_sin_nv_base as
select
    v.docto,
    v.num_docto,
    min(v.fecha_emision)::date                                        as fecha,
    max(v.cliente)                                                    as cliente,
    max(v.rut)                                                        as rut,
    max(trim(coalesce(v.nom_vddor, '') || ' ' || coalesce(v.apell_vddor, ''))) as vendedor,
    round(sum(coalesce(v.total_neto, 0)))::bigint                     as total_neto,
    count(*)                                                          as n_lineas,
    'ventas_full'::text                                               as fuente
from shg_dashboards.ventas_full v
where v.nota_venta is null
group by v.docto, v.num_docto
union all
select
    f.docto, f.num_docto, f.fecha::date, f.cliente, f.rut, f.vendedor,
    round(coalesce(f.total_neto, 0))::bigint, coalesce(f.n_lineas, 0), 'facturas_manager'::text
from shg_dashboards.facturas_manager f
where f.nota_venta is null
  and coalesce(f.nula, 0) = 0
  and f.docto in ('FAV', 'BOV', 'NDV', 'NCV')
  and f.fecha >= date_trunc('year', current_date)
  and not exists (select 1 from shg_dashboards.ventas_full v where v.docto = f.docto and v.num_docto = f.num_docto);

create or replace view shg_dashboards.trazabilidad_nv_auto as
with con_nv as (
    -- Facturas con NV conocida (Ventas Full o manual) y su RUT
    select v.docto, v.num_docto, min(v.fecha_emision)::date as fecha, max(v.rut) as rut,
           max(coalesce(v.nota_venta, m.nota_venta)) as nota_venta
    from shg_dashboards.ventas_full v
    left join shg_dashboards.facturas_nv_manual m on m.docto = v.docto and m.num_docto = v.num_docto
    where coalesce(v.nota_venta, m.nota_venta) is not null and v.docto in ('FAV', 'BOV', 'NDV')
    group by v.docto, v.num_docto
    union all
    select f.docto, f.num_docto, f.fecha::date, f.rut, coalesce(f.nota_venta, m.nota_venta)
    from shg_dashboards.facturas_manager f
    left join shg_dashboards.facturas_nv_manual m on m.docto = f.docto and m.num_docto = f.num_docto
    where coalesce(f.nota_venta, m.nota_venta) is not null
      and coalesce(f.nula, 0) = 0 and f.docto in ('FAV', 'BOV', 'NDV')
      and f.fecha >= date_trunc('year', current_date)
      and not exists (select 1 from shg_dashboards.ventas_full v where v.docto = f.docto and v.num_docto = f.num_docto)
),
pend as (
    -- Saldo de cada NV sin contar las asociaciones automáticas
    select nv.numnota,
           nv.totneto - coalesce(sum(case when b.docto = 'NCV' then -b.total_neto else b.total_neto end), 0) as pendiente
    from shg_dashboards.notas_de_venta nv
    left join shg_dashboards.trazabilidad_nv_documentos_base b on b.nota_venta = nv.numnota
    group by nv.numnota, nv.totneto
)
select
    s.docto,
    s.num_docto,
    p.nota_venta                       as nv_auto,
    p.num_docto                        as doc_prev,
    p.fecha                            as fecha_prev,
    pe.pendiente                       as pendiente_nv
from shg_dashboards.trazabilidad_facturas_sin_nv_base s
left join shg_dashboards.facturas_nv_manual m on m.docto = s.docto and m.num_docto = s.num_docto
join lateral (
    select d.nota_venta, d.num_docto, d.fecha
    from con_nv d
    where d.rut = s.rut
      and d.num_docto < s.num_docto
      and d.fecha <= s.fecha
      and d.fecha >= s.fecha - 30
    order by d.num_docto desc
    limit 1
) p on true
join pend pe on pe.numnota = p.nota_venta and pe.pendiente > 1
where m.nota_venta is null
  and s.docto in ('FAV', 'BOV', 'NDV')
  and coalesce(s.rut, '') <> '';

create or replace view shg_dashboards.trazabilidad_nv_documentos as
select b.nota_venta, b.docto, b.num_docto, b.fecha, b.cliente, b.total_neto, b.factura_ref, b.n_lineas,
       b.asignacion_manual, false as asignacion_auto
from shg_dashboards.trazabilidad_nv_documentos_base b
union all
select a.nv_auto, s.docto, s.num_docto, s.fecha, s.cliente, s.total_neto, null::bigint, s.n_lineas,
       false, true
from shg_dashboards.trazabilidad_facturas_sin_nv_base s
join shg_dashboards.trazabilidad_nv_auto a on a.docto = s.docto and a.num_docto = s.num_docto;

create or replace view shg_dashboards.trazabilidad_nv as
with docs as (
    select
        d.nota_venta,
        d.docto,
        d.num_docto,
        d.fecha                                   as fecha_emision,
        d.cliente,
        d.total_neto::double precision            as total_neto,
        d.asignacion_manual,
        d.asignacion_auto
    from shg_dashboards.trazabilidad_nv_documentos d
),
vendedor_nv as (
    -- Vendedor según el primer documento del Ventas Full (como antes)
    select distinct on (coalesce(v.nota_venta, m.nota_venta))
        coalesce(v.nota_venta, m.nota_venta) as nota_venta,
        trim(coalesce(v.nom_vddor, '') || ' ' || coalesce(v.apell_vddor, '')) as vendedor
    from shg_dashboards.ventas_full v
    left join shg_dashboards.facturas_nv_manual m on m.docto = v.docto and m.num_docto = v.num_docto
    where coalesce(v.nota_venta, m.nota_venta) is not null
    order by coalesce(v.nota_venta, m.nota_venta), v.fecha_emision, v.num_docto
),
por_nv as (
    select
        nota_venta,
        sum(total_neto) filter (where docto in ('FAV', 'BOV', 'NDV'))              as facturado_bruto,
        sum(total_neto) filter (where docto = 'NCV')                               as notas_credito,
        count(distinct num_docto) filter (where docto in ('FAV', 'BOV', 'NDV'))    as n_facturas,
        string_agg(distinct num_docto::text, ', ') filter (where docto in ('FAV', 'BOV', 'NDV')) as facturas_lista,
        string_agg(distinct num_docto::text, ', ') filter (where docto = 'NCV')   as nc_lista,
        count(*) filter (where asignacion_manual)                                  as n_facturas_manual,
        count(*) filter (where asignacion_auto)                                    as n_facturas_auto
    from docs
    group by nota_venta
),
info_nv as (
    select distinct on (nota_venta) nota_venta, cliente
    from docs
    order by nota_venta, fecha_emision, num_docto
),
guias_por_nv as (
    select nota_de_venta, count(distinct guia_despacho) as n_guias
    from shg_dashboards.guias
    where nota_de_venta is not null
    group by nota_de_venta
)
select
    p.nota_venta                                                       as numnota,
    nv.fecha                                                           as fecha_nv,
    i.cliente                                                          as razon_social,
    vn.vendedor,
    nv.totneto                                                         as valor_nv,
    coalesce(p.facturado_bruto, 0)::double precision                   as despachado_bruto,
    round(coalesce(p.notas_credito, 0))::bigint                        as notas_credito,
    (coalesce(p.facturado_bruto, 0) - coalesce(p.notas_credito, 0))::double precision as despachado_neto,
    (coalesce(p.facturado_bruto, 0) - coalesce(p.notas_credito, 0) - nv.totneto)::double precision as diferencia,
    coalesce(round((coalesce(p.facturado_bruto, 0) - coalesce(p.notas_credito, 0))::numeric) > (nv.totneto + 1), false) as excede_valor_nv,
    p.n_facturas,
    coalesce(g.n_guias, 0)                                             as n_guias,
    p.facturas_lista,
    round(coalesce(p.notas_credito, 0) * 1.19)::bigint                 as notas_credito_iva,
    p.nc_lista,
    nv.numnota is not null                                             as nv_en_manager,
    p.n_facturas_manual,
    p.n_facturas_auto
from por_nv p
left join shg_dashboards.notas_de_venta nv on nv.numnota = p.nota_venta
left join info_nv i       on i.nota_venta = p.nota_venta
left join vendedor_nv vn  on vn.nota_venta = p.nota_venta
left join guias_por_nv g  on g.nota_de_venta = p.nota_venta;

-- ---------------------------------------------------------------------
-- 4. Facturas sin NV: documentos cuya NV Manager no conoce, con la
--    asociación manual (nv_asignada), la automática (nv_auto, doc_prev,
--    fecha_prev) y las NV candidatas del mismo RUT con saldo pendiente
--    (> $1), ordenadas de mayor a menor pendiente.
-- ---------------------------------------------------------------------
create or replace view shg_dashboards.trazabilidad_facturas_sin_nv as
with pend as (
    select
        nv.numnota,
        nv.rutfact                                                        as rut,
        nv.fecha                                                          as fecha_nv,
        nv.totneto                                                        as valor_nv,
        round(coalesce(t.despachado_neto, 0))::bigint                     as facturado,
        (nv.totneto - round(coalesce(t.despachado_neto, 0)))::bigint      as pendiente
    from shg_dashboards.notas_de_venta nv
    left join shg_dashboards.trazabilidad_nv t on t.numnota = nv.numnota
    where nv.totneto > 0
      and nv.totneto - round(coalesce(t.despachado_neto, 0)) > 1
),
cand as (
    select rut,
           jsonb_agg(jsonb_build_object('numnota', numnota, 'fecha_nv', fecha_nv, 'valor_nv', valor_nv,
                                        'facturado', facturado, 'pendiente', pendiente)
                     order by pendiente desc) as nv_candidatas
    from pend
    group by rut
)
select
    d.docto,
    d.num_docto,
    d.fecha,
    d.cliente,
    d.rut,
    d.vendedor,
    d.total_neto,
    d.n_lineas,
    d.fuente,
    m.nota_venta                                                          as nv_asignada,
    m.asignado_por,
    m.asignado_en,
    coalesce(c.nv_candidatas, '[]'::jsonb)                                as nv_candidatas,
    a.nv_auto,
    a.doc_prev,
    a.fecha_prev
from shg_dashboards.trazabilidad_facturas_sin_nv_base d
left join shg_dashboards.facturas_nv_manual m on m.docto = d.docto and m.num_docto = d.num_docto
left join cand c on c.rut = d.rut
left join shg_dashboards.trazabilidad_nv_auto a on a.docto = d.docto and a.num_docto = d.num_docto;

revoke all on shg_dashboards.trazabilidad_nv_documentos_base, shg_dashboards.trazabilidad_facturas_sin_nv_base,
              shg_dashboards.trazabilidad_nv_auto, shg_dashboards.trazabilidad_facturas_sin_nv,
              shg_dashboards.trazabilidad_nv_documentos from anon;
grant select on shg_dashboards.trazabilidad_nv_documentos_base, shg_dashboards.trazabilidad_facturas_sin_nv_base,
                shg_dashboards.trazabilidad_nv_auto, shg_dashboards.trazabilidad_facturas_sin_nv,
                shg_dashboards.trazabilidad_nv_documentos to authenticated, service_role;

-- Comprobación
-- select * from shg_dashboards.trazabilidad_nv_auto order by num_docto;
-- select count(*) filter (where nv_asignada is null and nv_auto is null) as sin_nv, count(*) as total
-- from shg_dashboards.trazabilidad_facturas_sin_nv;
