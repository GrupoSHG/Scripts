-- ============================================================================
-- Oficina de Agentes: cuatro Desarrolladores (dev, dev2, dev3, dev4)
-- ============================================================================
-- Complementa oficina_agentes.sql. La Oficina tiene ahora una "Oficina de Desarrollo" con cuatro
-- Desarrolladores, cada uno con su escritorio e historial, para dar instrucciones de código en
-- paralelo. Este archivo:
--   1. deja que shg_dashboards.agentes_instrucciones acepte dev2, dev3 y dev4;
--   2. sube de 6 a 10 las instrucciones abiertas a la vez que acepta public.agente_instruir.
-- Idempotente. Correr en el SQL Editor del proyecto ffxopvzxyeacpbtxuagu, o por CLI:
--   supabase --workdir <tmp> db query --linked -f automatizacion/oficina_agentes_desarrolladores.sql
-- ============================================================================

alter table shg_dashboards.agentes_instrucciones drop constraint if exists agentes_instrucciones_agente_check;
alter table shg_dashboards.agentes_instrucciones add constraint agentes_instrucciones_agente_check
  check (agente in ('comercial', 'finanzas', 'planta', 'dev', 'dev2', 'dev3', 'dev4'));

create or replace function public.agente_instruir(p_agente text, p_texto text, p_parametros jsonb default '{}'::jsonb)
returns jsonb language plpgsql security definer set search_path = shg_dashboards, automatizacion, public as $$
declare
  v_id bigint;
  v_quien text := coalesce(auth.jwt() ->> 'email', auth.uid()::text);
  v_abiertas int;
begin
  if auth.uid() is null then raise exception 'Hay que iniciar sesión'; end if;
  if not shg_dashboards.es_director() then
    raise exception 'Solo admin y directores pueden dar instrucciones a los agentes' using errcode = '42501';
  end if;
  select count(*) into v_abiertas from shg_dashboards.agentes_instrucciones
   where estado in ('pendiente', 'trabajando') and creada > now() - interval '1 hour';
  if v_abiertas >= 10 then
    raise exception 'Ya hay % instrucciones en curso; espera a que terminen.', v_abiertas;
  end if;

  insert into shg_dashboards.agentes_instrucciones (agente, texto, parametros, pedido_por, pedido_por_uid)
  values (p_agente, btrim(p_texto), coalesce(p_parametros, '{}'::jsonb), v_quien, auth.uid())
  returning id into v_id;

  perform automatizacion.disparar('agente-ia.yml', jsonb_build_object('instruccion', v_id::text), v_quien);
  return jsonb_build_object('ok', true, 'id', v_id);
end $$;
revoke all on function public.agente_instruir(text, text, jsonb) from public, anon;
grant execute on function public.agente_instruir(text, text, jsonb) to authenticated;
