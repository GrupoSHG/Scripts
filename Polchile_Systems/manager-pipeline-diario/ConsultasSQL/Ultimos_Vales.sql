-- Último N° de vale de ingreso (tipo 5) y de salida (tipo 6) de Manager.
-- Lo usa shg_dashboards.generar_vales_manager() (GrupoSHG_Systems,
-- Polchile_Systems/dashboard-produccion/vales_manager.sql) para numerar los
-- vales que arma con el avance de planta. Se ignoran los N° tipeados fuera de
-- serie (≥ 1.000.000).
SELECT
    d.TIPODOC      AS tipodoc,
    MAX(d.NUMFACT) AS ultimo,
    MAX(d.FECHA)   AS fecha
FROM DOCU_DB d
WHERE d.TIPODOC IN (5, 6)
  AND d.NUMFACT < 1000000
GROUP BY d.TIPODOC;
