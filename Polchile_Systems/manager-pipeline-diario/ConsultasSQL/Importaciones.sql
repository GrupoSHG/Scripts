-- ============================================================================
-- Importaciones.sql — histórico de órdenes de compra (compras e importaciones)
-- ============================================================================
-- Una fila por línea de orden de compra desde el 1 de enero de 2024, con lo
-- pedido, lo recibido y lo pendiente. Alimenta la tabla
-- shg_dashboards.importaciones (la crea el cargador masivo del pipeline diario:
-- la hoja del Excel se llama igual que este archivo) y la sección
-- "Importaciones · histórico de órdenes de compra" del Dashboard Producción,
-- que filtra por proveedor, familia y estado.
--
-- Criterio de "pendiente": CANTIDAD - CANTRECI > 0, el mismo que usa
-- Consumos_acero.sql para el "Por llegar" de los aceros.
-- familia: 'Acero' (código AC%), 'Poliestireno' (código POL% o nombre con
-- "poliestireno") u 'Otro'. Sin filtro de familia: así el dashboard también
-- muestra las compras locales (poliestireno, insumos) y el usuario elige.
-- ============================================================================

DECLARE @FechaInicio DATE = '2024-01-01';

SELECT
    oc.NUMOC                                                   AS numoc,
    CAST(oc.FECHA AS DATE)                                     AS fecha,
    oc.RUTPROV                                                 AS rut_proveedor,
    LTRIM(RTRIM(ISNULL(cli.RAZSOC, 'Proveedor sin nombre')))   AS proveedor,
    od.ITEM                                                    AS item,
    LTRIM(RTRIM(ISNULL(art.CODIGO, '')))                       AS codigo,
    LTRIM(RTRIM(ISNULL(od.DESCRIP, art.NOMBRE)))               AS descripcion,
    CASE
        WHEN art.CODIGO LIKE 'AC%'                                        THEN 'Acero'
        WHEN art.CODIGO LIKE 'POL%' OR art.NOMBRE LIKE '%oliestireno%'    THEN 'Poliestireno'
        ELSE 'Otro'
    END                                                        AS familia,
    art.UNIDMED                                                AS unidad,
    CAST(od.CANTIDAD AS DECIMAL(18,4))                         AS cantidad,
    CAST(ISNULL(od.CANTRECI, 0) AS DECIMAL(18,4))              AS cantidad_recibida,
    CAST(od.CANTIDAD - ISNULL(od.CANTRECI, 0) AS DECIMAL(18,4)) AS cantidad_pendiente,
    CASE
        WHEN ISNULL(od.CANTRECI, 0) <= 0                 THEN 'Pendiente'
        WHEN ISNULL(od.CANTRECI, 0) < od.CANTIDAD        THEN 'Parcial'
        ELSE 'Recibida'
    END                                                        AS estado,
    CAST(od.PRECUNIT AS DECIMAL(18,4))                         AS precio_unitario,
    CAST(od.CANTIDAD * od.PRECUNIT AS DECIMAL(18,2))           AS total_neto,
    oc.TASAREF                                                 AS tasa_cambio,
    od.CENTCC                                                  AS centro_costo

FROM OC_DB oc
    INNER JOIN OCDET_DB od  ON oc.NUMREG  = od.NUMRECOR
    LEFT  JOIN ART_DB   art ON od.NCODART = art.NREGUIST
    LEFT  JOIN CLIEN_DB cli ON oc.NRUTPROV = cli.NREGUIST

WHERE oc.FECHA >= @FechaInicio
  AND od.CANTIDAD > 0

ORDER BY oc.FECHA DESC, oc.NUMOC DESC, od.ITEM;
