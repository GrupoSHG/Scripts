-- Timeout de las RPC que llama el robot (cargar.py -> shg_dashboards.reemplazar_<tabla>).
--
-- Supabase entra a la base con el rol `authenticator`, que trae
-- statement_timeout = 8s y lock_timeout = 8s, y después hace SET ROLE al rol del
-- token. `anon` tiene 3s y `authenticated` 8s; `service_role` no define nada, así
-- que hereda los 8s del authenticator. Las funciones reemplazar_* (borrar e insertar
-- 3.500-4.000 filas desde un jsonb) tardan entre 0,3 y 7,7 s según la carga de la
-- instancia, y cuando pasan de 8 s Postgres las cancela:
--
--   {"code":"57014","message":"canceling statement due to statement timeout"}
--
-- Solo el service_role (scripts de GitHub Actions y los Apps Script con clave de
-- servicio) recibe un límite más holgado; los dashboards siguen con 3 s / 8 s.
-- Se aplica a mano en el SQL Editor; el NOTIFY hace que PostgREST relea la
-- configuración de los roles sin esperar al próximo reinicio.

alter role service_role set statement_timeout = '120s';
notify pgrst, 'reload config';

-- Comprobar:
--   select rolname, rolconfig from pg_roles
--    where rolname in ('authenticator', 'anon', 'authenticated', 'service_role');
