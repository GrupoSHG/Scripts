-- HEA (Hojalatería El Abuelo): acceso solo para quienes están en hea.profiles.
--
-- Antes (estado vivo al 18/11/2026):
--   * ots, ocs, depositos, productos: política PERMISIVA "<tabla>_all_authenticated"
--     (using true) → cualquier usuario con sesión del login compartido leía y
--     escribía HEA (solo lo frenaban las restrictivas de vendedor y cliente).
--   * profiles_select: using true → cualquiera veía la lista de correos.
--   * profiles_update_own_basic: cada usuario podía editar SU fila sin restringir
--     columnas → podía subirse solo a superadmin.
--   * El sitio daba rol superadmin por defecto a quien no tenía perfil.
--
-- Después:
--   * hea.es_miembro(): hay fila en hea.profiles para auth.uid().
--   * Tablas de negocio: "<tabla>_miembros_hea" (using/with check es_miembro()).
--     Las restrictivas sin_clientes_externos / vendedor_solo_lo_suyo se mantienen.
--   * profiles: cada uno ve su fila; los miembros ven todas. Solo superadmin
--     modifica (UPDATE), inserta y borra.
--   * hea.agregar_miembro(email, rol): para el botón "Agregar usuario" del sitio;
--     solo superadmin, busca el usuario en auth.users por correo.
--
-- No afecta: Cockpit (getResumenHEA con service_role), Directorio/Oficina de
-- Agentes (agentes_lectura, BYPASSRLS).
--
-- Aplicar ANTES de publicar el index.html nuevo (el sitio usa agregar_miembro).
-- Aplicar: supabase --workdir <tmp> db query --linked -f hea_acceso_miembros.sql

begin;

create or replace function hea.es_miembro()
returns boolean
language sql stable security definer
set search_path = ''
as $$
  select exists (select 1 from hea.profiles where id = auth.uid())
$$;
revoke all on function hea.es_miembro() from public, anon;
grant execute on function hea.es_miembro() to authenticated;

-- Misma lógica que antes, con search_path fijo (era SECURITY DEFINER sin él).
create or replace function hea."current_role"()
returns text
language sql stable security definer
set search_path = ''
as $$
  select role from hea.profiles where id = auth.uid()
$$;
revoke all on function hea."current_role"() from public, anon;
grant execute on function hea."current_role"() to authenticated;

do $$
declare t text;
begin
  foreach t in array array['ots','ocs','depositos','productos'] loop
    execute format('drop policy if exists %I on hea.%I', t || '_all_authenticated', t);
    execute format('drop policy if exists %I on hea.%I', t || '_miembros_hea', t);
    execute format(
      'create policy %I on hea.%I for all to authenticated
         using ((select hea.es_miembro())) with check ((select hea.es_miembro()))',
      t || '_miembros_hea', t);
  end loop;
end $$;

drop policy if exists profiles_select on hea.profiles;
create policy profiles_select on hea.profiles for select to authenticated
  using (id = (select auth.uid()) or (select hea.es_miembro()));

drop policy if exists profiles_update_own_basic on hea.profiles;
drop policy if exists profiles_update_superadmin on hea.profiles;
create policy profiles_update_superadmin on hea.profiles for update to authenticated
  using ((select hea."current_role"()) = 'superadmin')
  with check ((select hea."current_role"()) = 'superadmin');

create or replace function hea.agregar_miembro(p_email text, p_rol text default 'user')
returns uuid
language plpgsql security definer
set search_path = ''
as $$
declare v_id uuid; v_email text;
begin
  if hea."current_role"() is distinct from 'superadmin' then
    raise exception 'Solo un superadmin puede agregar usuarios a HEA';
  end if;
  if p_rol not in ('superadmin','admin','user') then
    raise exception 'Rol inválido: %', p_rol;
  end if;
  select u.id, u.email into v_id, v_email
    from auth.users u where lower(u.email) = lower(trim(p_email));
  if v_id is null then
    raise exception 'No existe un usuario con el correo %', p_email;
  end if;
  insert into hea.profiles (id, email, role) values (v_id, v_email, p_rol)
  on conflict (id) do update set role = excluded.role, email = excluded.email;
  return v_id;
end $$;
revoke all on function hea.agregar_miembro(text, text) from public, anon;
grant execute on function hea.agregar_miembro(text, text) to authenticated;

commit;

-- Verificación:
--   select tablename, policyname, permissive, cmd from pg_policies where schemaname = 'hea' order by 1, 2;
--
-- Volver atrás (solo tablas de negocio):
--   do $$ declare t text; begin foreach t in array array['ots','ocs','depositos','productos'] loop
--     execute format('drop policy if exists %I on hea.%I', t||'_miembros_hea', t);
--     execute format('create policy %I on hea.%I for all to authenticated using (true) with check (true)', t||'_all_authenticated', t);
--   end loop; end $$;
