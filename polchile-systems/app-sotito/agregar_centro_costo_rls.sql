-- Falta el permiso de escritura para poder crear centros de costo desde la app
-- (antes solo tenía política de lectura). Correr en el proyecto ffxopvzxyeacpbtxuagu.

create policy "Escritura pública centros_costo"
on centros_costo for insert
with check (true);

grant insert on centros_costo to anon, authenticated;
