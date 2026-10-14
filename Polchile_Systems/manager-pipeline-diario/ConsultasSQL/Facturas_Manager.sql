-- =====================================================================
-- Facturas_Manager.sql  ->  shg_dashboards.facturas_manager  (una fila por documento)
--
-- Todas las facturas (FAV), boletas (BOV), notas de débito (NDV) y notas
-- de crédito (NCV) de venta emitidas desde el 01-01-2025, con la Nota de
-- Venta a la que pertenecen cuando Manager la conoce.
--
-- A diferencia del Ventas Full (una fila por línea y solo líneas con
-- artículo real), acá entra TODO documento emitido, también los que usan
-- el artículo genérico "-" o no referencian ninguna NV. Es la base para
-- que Trazabilidad NV muestre las facturas sin NV y permita asociarlas a
-- mano (vista shg_dashboards.trazabilidad_facturas_sin_nv).
--
-- NOTA_VENTA se resuelve en este orden (mismo criterio que Ventas_Full.sql):
--   1. NV más frecuente entre las líneas del documento
--      (DOCDE_DB.SQNVDET -> NOTDE_DB -> NOTV_DB.NUMNOTA, o la guía de
--      origen DOCDE_DB.SQGDDET -> DOCU_DB.NROPEDIDO)
--   2. NROPEDIDO de la cabecera del documento
--   3. Notas de crédito: NV de la factura referenciada (DOCU_DB.NUMFV)
-- ORIGEN_NV dice cuál de los tres aplicó ('lineas', 'cabecera',
-- 'factura_ref') o queda NULL si el documento no tiene NV.
--
-- Tipos: los montos van CAST a float para que lleguen a Supabase como
-- double precision (pyodbc entrega Decimal para money/numeric y pandas
-- los dejaría como texto); NOTA_VENTA / FACTURA_REF / NUMGUIAF se cargan
-- en columnas bigint ya creadas (supabase/facturas_sin_nv.sql).
--
-- OJO: se llama facturas_manager porque shg_dashboards.facturas ya existe y es
-- la tabla de facturas (OCR) de la App CyS; el pipeline la recrearia y borraria.
-- =====================================================================
WITH NV_LINEA AS (
    SELECT dd.NUMRECOR,
           COALESCE(nvl.NUMNOTA,
                    TRY_CONVERT(int, NULLIF(LTRIM(RTRIM(g.NROPEDIDO)), ''))) AS NV
    FROM DOCDE_DB dd
    INNER JOIN DOCU_DB d ON d.NUMREG = dd.NUMRECOR
    LEFT JOIN NOTDE_DB nd  ON dd.SQNVDET <> 0 AND nd.SEQNVDET = dd.SQNVDET
    LEFT JOIN NOTV_DB  nvl ON nvl.NUMREG = nd.NUMRECOR
    LEFT JOIN DOCU_DB  g   ON dd.SQGDDET <> 0 AND g.NUMREG = dd.SQGDDET AND g.TIPODOC = 2
    WHERE d.TIPODOC IN (1, 3, 4, 79)
      AND d.FECHA >= CONVERT(datetime, '01/01/2025', 103)
),
NV_DOC AS (
    SELECT NUMRECOR, NV,
           ROW_NUMBER() OVER (PARTITION BY NUMRECOR ORDER BY COUNT(*) DESC, NV) AS RN
    FROM NV_LINEA
    WHERE NV IS NOT NULL
    GROUP BY NUMRECOR, NV
)
SELECT
    CASE d.TIPODOC WHEN 1 THEN 'FAV' WHEN 3 THEN 'BOV' WHEN 79 THEN 'NDV' WHEN 4 THEN 'NCV' END AS DOCTO,
    CAST(d.NUMFACT AS bigint)                                              AS NUM_DOCTO,
    CAST(d.NUMREG  AS bigint)                                              AS NUMREG,
    d.FECHA                                                                AS FECHA,
    d.VENCIMIE                                                             AS FECHA_VENCIMIENTO,
    CAST(ISNULL(d.NULA, 0) AS int)                                         AS NULA,
    LTRIM(RTRIM(ISNULL(d.RUTFACT, '')))                                    AS RUT,
    SUBSTRING(ISNULL(c.RAZSOC, ''), 1, 60)                                 AS CLIENTE,
    LTRIM(RTRIM(ISNULL(p.CODIGO, '')))                                     AS COD_VDDOR,
    LTRIM(RTRIM(RTRIM(ISNULL(p.NOMBRE, '')) + ' ' + LTRIM(ISNULL(p.APELLIDO, '')))) AS VENDEDOR,
    CAST(ISNULL(d.TOTNETO, 0) AS float)                                    AS TOTAL_NETO,
    CAST(ISNULL(d.TOTIVA, 0)  AS float)                                    AS TOTAL_IVA,
    CAST(ISNULL(d.TOTAL, 0)   AS float)                                    AS TOTAL,
    NULLIF(LTRIM(RTRIM(ISNULL(d.NROPEDIDO, ''))), '')                      AS NROPEDIDO,
    COALESCE(nvd.NV,
             TRY_CONVERT(int, NULLIF(LTRIM(RTRIM(d.NROPEDIDO)), '')),
             TRY_CONVERT(int, NULLIF(LTRIM(RTRIM(fr.NROPEDIDO)), '')),
             frl.NV)                                                       AS NOTA_VENTA,
    CASE
        WHEN nvd.NV IS NOT NULL THEN 'lineas'
        WHEN TRY_CONVERT(int, NULLIF(LTRIM(RTRIM(d.NROPEDIDO)), '')) IS NOT NULL THEN 'cabecera'
        WHEN TRY_CONVERT(int, NULLIF(LTRIM(RTRIM(fr.NROPEDIDO)), '')) IS NOT NULL
             OR frl.NV IS NOT NULL THEN 'factura_ref'
    END                                                                    AS ORIGEN_NV,
    CAST(fr.NUMFACT AS bigint)                                             AS FACTURA_REF,
    TRY_CONVERT(bigint, d.NUMGUIAF)                                        AS NUMGUIAF,
    (SELECT COUNT(*) FROM DOCDE_DB dd WHERE dd.NUMRECOR = d.NUMREG)        AS N_LINEAS,
    LTRIM(RTRIM(ISNULL(d.GLOSACON, '')))                                   AS GLOSA
FROM DOCU_DB d
LEFT JOIN CLIEN_DB c   ON c.NREGUIST = d.NRUTCLIE
LEFT JOIN PERSO_DB p   ON p.NUMREG   = d.CODVEND
LEFT JOIN NV_DOC   nvd ON nvd.NUMRECOR = d.NUMREG AND nvd.RN = 1
LEFT JOIN DOCU_DB  fr  ON d.TIPODOC = 4 AND ISNULL(d.NUMFV, 0) <> 0 AND fr.NUMREG = d.NUMFV
LEFT JOIN NV_DOC   frl ON frl.NUMRECOR = fr.NUMREG AND frl.RN = 1
WHERE d.TIPODOC IN (1, 3, 4, 79)
  AND d.FECHA >= CONVERT(datetime, '01/01/2025', 103)
ORDER BY d.FECHA, d.NUMFACT
