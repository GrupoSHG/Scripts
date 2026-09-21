-- =====================================================
-- NV_Supabase.sql
-- Query dedicada exclusivamente a alimentar sync_supabase.py
-- (independiente de Notas_de_venta.sql, que sigue igual para Sheets/Drive)
-- Columnas confirmadas: NOTV_DB.TOTNETO, CLIEN_DB.NREGUIST / RAZSOC
-- =====================================================

SELECT
    nv.NUMNOTA   AS numero_nv,
    c.RAZSOC     AS cliente,
    nv.TOTNETO   AS monto_neto,
    nv.FECHA     AS fecha_nv,
    nv.APROBADA  AS aprobada
FROM NOTV_DB nv
LEFT JOIN CLIEN_DB c ON c.NREGUIST = nv.NRUTCLIE
WHERE nv.APROBADA = 1
ORDER BY nv.NUMNOTA DESC;