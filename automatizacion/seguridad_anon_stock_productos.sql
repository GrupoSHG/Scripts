-- ============================================================================
-- Seguridad, fase 3: stock_productos sin acceso anónimo (24/11/2026)
-- ============================================================================
-- La fase 2 (seguridad_anon_fase2.sql) cerró shg_dashboards, app_cys y hea, pero
-- dejó stock_productos fuera. Medido el 24/11/2026 en la base viva:
--   - anon tiene USAGE en el esquema y SELECT/INSERT/UPDATE/DELETE en las 13 tablas.
--   - 13 políticas "to public" (o sea, también anónimas): lectura en asistencia,
--     centros_costo, facturacion, facturas, gastos, iniciativas y personas, y
--     ESCRITURA en asistencia, facturas y gastos (ALL), personas y centros_costo
--     (INSERT) y BORRADO en facturas. Con la clave publicable, que va en el JS de
--     los sitios, cualquiera podía leer, escribir o borrar esas filas.
--
-- Quién usa el esquema (revisado en GrupoSHG_Systems, Scripts y el repo de la app
-- de Stock):
--   - stock: lo escriben el robot de Manager y el pipeline diario con la clave de
--     servicio; lo leen usuarios con sesión (Cockpit, tablets, Directorio, app de Stock).
--   - catalogo, stock, productos_segunda, ventas, aceros, profiles: la app de Stock,
--     siempre después de su login (getSession / signInWithPassword).
--   - personas, asistencia, centros_costo, facturas, gastos, facturacion,
--     iniciativas: copia vieja de las tablas de CyS. Ningún código las usa y no
--     registran escrituras (pg_stat_user_tables en 0 al 24/11/2026).
--
-- Qué hace:
--   1. Quita a anon todo acceso al esquema (como la fase 2 en los otros esquemas):
--      las políticas "to public" siguen sirviendo para usuarios con sesión.
--   2. Borra las 5 políticas de escritura abierta de la copia vieja de CyS: nadie
--      escribe ahí, y con ellas cualquier usuario con sesión podía hacerlo.
-- La clave de servicio no cambia (service_role ignora RLS y conserva sus GRANT).
--
-- Después de aplicarlo, verificar:
--   - Con la clave publicable, GET /rest/v1/stock?select=codigo&limit=1 con
--     Accept-Profile: stock_productos → 401 "permission denied for schema".
--   - La app de Stock (productosstock.netlify.app) con sesión muestra el stock.
--   - La próxima corrida del robot de Manager carga stock_productos.stock.
-- Reversión: grant usage on schema stock_productos to anon; grant select on
-- <tabla> to anon; y recrear la política borrada (texto abajo).
-- Idempotente; aplicar a mano con la CLI o el SQL Editor.
-- ============================================================================

begin;

-- 1. Sin acceso anónimo
revoke all on all tables in schema stock_productos from anon;
revoke all on all sequences in schema stock_productos from anon;
revoke all on all functions in schema stock_productos from anon;
revoke usage on schema stock_productos from anon;
alter default privileges in schema stock_productos revoke all on tables from anon;
alter default privileges in schema stock_productos revoke all on sequences from anon;
alter default privileges in schema stock_productos revoke all on functions from anon;

-- 2. Sin escritura abierta en la copia vieja de CyS
--    (eran: for all to public using (true) with check (true) en asistencia,
--     facturas y gastos; for insert to public with check (true) en personas y
--     centros_costo; for delete to public using (true) en facturas)
drop policy if exists "Escritura pública" on stock_productos.asistencia;
drop policy if exists "Escritura pública" on stock_productos.facturas;
drop policy if exists "Borrado público facturas" on stock_productos.facturas;
drop policy if exists "Escritura pública" on stock_productos.gastos;
drop policy if exists "Escritura pública" on stock_productos.personas;
drop policy if exists "Escritura pública centros_costo" on stock_productos.centros_costo;

commit;
