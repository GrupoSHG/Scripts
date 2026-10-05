-- Una fila por cada combinación (acero, proveedor) con la cantidad
-- pendiente de recibir de ESE proveedor específico para ESE acero.
-- Mismo criterio de "pendiente" que ya usa Consumos_acero.sql:
-- CANTIDAD - CANTRECI > 0 (lo que falta por recibir de esa línea de OC).
--
-- Formato "largo" a propósito (no pivoteado aquí) — la lista de
-- proveedores cambia con el tiempo, así que el pivote a columnas se hace
-- en el frontend, no en el SQL, para no depender de una estructura fija.

SELECT
    a.CODIGO                                            AS codigo_acero,
    a.NOMBRE                                             AS descripcion_acero,
    ISNULL(cli.RAZSOC, 'Proveedor sin nombre')            AS proveedor,
    CAST(SUM(od.CANTIDAD - od.CANTRECI) AS DECIMAL(18,4)) AS cantidad_pendiente

FROM OCDET_DB od
    INNER JOIN OC_DB    oc  ON oc.NUMREG    = od.NUMRECOR
    INNER JOIN ART_DB   a   ON a.NREGUIST   = od.NCODART
    LEFT JOIN  CLIEN_DB cli ON oc.NRUTPROV  = cli.NREGUIST

WHERE (od.CANTIDAD - od.CANTRECI) > 0
  AND a.CODIGO LIKE 'AC%'
  AND a.NOMBRE LIKE '%Acero%'

GROUP BY a.CODIGO, a.NOMBRE, cli.RAZSOC
ORDER BY a.CODIGO, proveedor;
