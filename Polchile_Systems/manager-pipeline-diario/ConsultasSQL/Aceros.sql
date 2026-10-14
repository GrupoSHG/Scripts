DECLARE @FechaInicio DATE = '2026-01-01';
DECLARE @FechaFin    DATE = CAST(GETDATE() AS DATE);

SELECT
    art.codigo                                              AS codigo,
    art.nombre                                              AS producto,
    art.UNIDMED                                             AS unidad,
    ROUND(AVG(monthly.cantidad_mensual), 2)                 AS promedio_cantidad_mensual
FROM (
    SELECT
        art2.NREGUIST,
        YEAR(d.FECHA)                          AS anio,
        MONTH(d.FECHA)                         AS mes,
        CAST(SUM(dd.cantidad) AS FLOAT)        AS cantidad_mensual,
        CAST(SUM(dd.CANTIDAD * art2.VALPROM) AS FLOAT) AS cto_mensual
    FROM DOCU_DB d
        INNER JOIN DOCDE_DB dd   ON d.NUMREG    = dd.NUMRECOR
        INNER JOIN ART_DB   art2 ON dd.NCODART  = art2.NREGUIST
        INNER JOIN CHOI_DB  ch   ON dd.BODEGA   = ch.NUMREG
        LEFT  JOIN OTDET_DB od   ON dd.SQOTDET  = od.SQLINE
        LEFT  JOIN ORDTR_DB ot   ON ot.NSEQ     = od.OTSEQ
    WHERE d.tipodoc = 6
      AND (art2.codigo LIKE 'AC1065%'
        OR art2.codigo LIKE 'AC1219%')
      AND art2.nombre LIKE '%ACERO%'
      AND d.FECHA >= @FechaInicio
      AND d.FECHA <  @FechaFin
      AND d.NULA = 0
    GROUP BY
        art2.NREGUIST,
        YEAR(d.FECHA),
        MONTH(d.FECHA)
) monthly
    INNER JOIN ART_DB art ON monthly.NREGUIST = art.NREGUIST
GROUP BY
    art.codigo,
    art.nombre,
    art.UNIDMED
ORDER BY
    art.codigo;