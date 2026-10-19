-- =====================================================================
-- Compras_Manager.sql  ->  shg_dashboards.compras_manager  (una fila por línea)
--
-- Documentos de compra registrados en Manager desde el 01-01-2025:
-- facturas de proveedor (TIPODOC 8 = FAC), guías de recepción (9 = GDR) y
-- notas de crédito de proveedor (10 = NCC), con cada línea tal como quedó
-- en Manager: artículo, cantidad, precio, cuenta contable, centro de costo
-- y bodega (códigos, no ids internos).
--
-- Lo usa la pantalla RCV · SII del Dashboard Finanzas para:
--   1. el calce: qué facturas del RCV del SII ya están en Manager
--      (RUT proveedor + folio + tipo) y cuáles faltan;
--   2. proponer, para las que faltan, el artículo de gasto, la cuenta
--      contable, el centro de costo y la bodega que se usaron la última
--      vez con ese proveedor, y así armar el archivo de importación
--      (Abastecimiento > Otros Procesos > Importar Doc Compras).
--
-- Códigos: la bodega está en CHOI_DB con TIPO = 9 (DOCDE_DB.BODEGA es su
-- NUMREG); el centro de costo en CENT_DB; la cuenta en PLAN_DB.
-- Montos CAST a float para que lleguen como double precision (pyodbc
-- entrega Decimal y pandas lo dejaría como texto).
-- =====================================================================
SELECT
    CASE d.TIPODOC WHEN 8 THEN 'FAC' WHEN 9 THEN 'GDR' WHEN 10 THEN 'NCC' END AS DOCTO,
    CAST(d.TIPODOC AS int)                                             AS TIPODOC,
    CAST(d.NUMFACT AS bigint)                                          AS NUM_DOCTO,
    CAST(d.NUMREG  AS bigint)                                          AS NUMREG,
    d.FECHA                                                            AS FECHA,
    d.VENCIMIE                                                         AS FECHA_VENCIMIENTO,
    LTRIM(RTRIM(ISNULL(d.RUTFACT, '')))                                AS RUT,
    SUBSTRING(ISNULL(c.RAZSOC, ''), 1, 60)                             AS PROVEEDOR,
    CAST(ISNULL(d.ESELECTR, 0) AS int)                                 AS ES_ELECTRONICO,
    CAST(ISNULL(d.NULA, 0) AS int)                                     AS NULA,
    CASE WHEN ISNULL(d.AFECTO, 0) = 0 AND ISNULL(d.EXENTO, 0) > 0 THEN 0 ELSE 1 END AS AFECTO,
    CAST(ISNULL(d.TOTNETO, 0) AS float)                                AS TOTAL_NETO,
    CAST(ISNULL(d.EXENTO, 0)  AS float)                                AS TOTAL_EXENTO,
    CAST(ISNULL(d.TOTIVA, 0)  AS float)                                AS TOTAL_IVA,
    CAST(ISNULL(d.TOTAL, 0)   AS float)                                AS TOTAL,
    LTRIM(RTRIM(ISNULL(d.MONEDA, '$')))                                AS MONEDA,
    CAST(ISNULL(d.SUCUR, 1) AS int)                                    AS SUCURSAL,
    NULLIF(LTRIM(RTRIM(ISNULL(d.NUMORDENC, ''))), '')                  AS ORDEN_COMPRA,
    LTRIM(RTRIM(ISNULL(d.GLOSACON, '')))                               AS GLOSA,
    CAST(dd.SEQLINE AS bigint)                                         AS LINEA,
    LTRIM(RTRIM(ISNULL(a.CODIGO, '')))                                 AS ARTICULO,
    SUBSTRING(ISNULL(dd.DESCRIP, ''), 1, 60)                           AS DESCRIPCION,
    CAST(ISNULL(dd.CANTIDAD, 0) AS float)                              AS CANTIDAD,
    CAST(ISNULL(dd.PRECUNIT, 0) AS float)                              AS PRECIO_UNITARIO,
    LTRIM(RTRIM(ISNULL(p.CODIGO, '')))                                 AS CUENTA_CONTABLE,
    LTRIM(RTRIM(ISNULL(ce.CODIGO, '')))                                AS CENTRO_COSTO,
    LTRIM(RTRIM(ISNULL(bo.CODIGO, '')))                                AS BODEGA
FROM DOCU_DB d
INNER JOIN DOCDE_DB dd ON dd.NUMRECOR = d.NUMREG
LEFT JOIN CLIEN_DB c   ON c.NREGUIST = d.NRUTCLIE
LEFT JOIN ART_DB   a   ON a.NREGUIST = dd.NCODART
LEFT JOIN PLAN_DB  p   ON p.NREGUIST = dd.CTACTBLE
LEFT JOIN CENT_DB  ce  ON ce.NREGUIST = dd.CENCOSTO
LEFT JOIN CHOI_DB  bo  ON bo.NUMREG = dd.BODEGA AND bo.TIPO = 9
WHERE d.TIPODOC IN (8, 9, 10)
  AND d.FECHA >= CONVERT(datetime, '01/01/2025', 103)
ORDER BY d.FECHA, d.NUMFACT, dd.SEQLINE
