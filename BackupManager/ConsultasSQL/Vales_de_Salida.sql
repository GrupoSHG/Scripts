

DECLARE @FechaInicio DATE = '2026-01-01';
DECLARE @FechaFin    DATE = CAST(GETDATE() AS DATE);

SELECT DISTINCT
    CASE WHEN d.tipodoc = 6 THEN 'vs' ELSE 'vi' END  AS tipo_vale,
    CASE WHEN dd.SQOTDET > 0 THEN 'Con OT' ELSE 'Sin OT' END AS origen,
    d.numfact                          AS num_docto,
    d.FECHA                            AS FECHA_VS,
    ot.PRP                             AS NOTA_VTA,
    ot.FECHAIN                         AS FECHA_OP,
    ISNULL(ot.NUMOT, dd.NUMOT)         AS OP,
    SUBSTRING(d.glosacon, 1, 50)       AS glosa_doc,
    SUBSTRING(od.GLOSA, 1, 50)         AS glosa_ot,
    art.codigo                         AS codigo,
    art.nombre                         AS producto,
    SUBSTRING(art.CLASE1, 1, 15)       AS CLASE1,
    SUBSTRING(art.CLASE2, 1, 15)       AS CLASE2,
    SUBSTRING(art.CLASE3, 1, 15)       AS CLASE3,
    SUBSTRING(art.CLASE4, 1, 15)       AS CLASE4,
    dd.cantidad                        AS cantidad,
    art.UNIDMED                        AS UNIDMED,
    SUBSTRING(ch.DESCRIP, 1, 50)       AS BODEGA,
    art.VALPROM                        AS CTO_UNIT,
    dd.CANTIDAD * art.VALPROM          AS cto_TOTAL_VSALIDA

FROM DOCU_DB d
    INNER JOIN DOCDE_DB dd  ON d.NUMREG    = dd.NUMRECOR
    INNER JOIN ART_DB   art ON dd.NCODART  = art.NREGUIST
    INNER JOIN CHOI_DB  ch  ON dd.BODEGA   = ch.NUMREG
    LEFT  JOIN OTDET_DB od  ON dd.SQOTDET  = od.SQLINE
    LEFT  JOIN ORDTR_DB ot  ON ot.NSEQ     = od.OTSEQ

WHERE d.tipodoc IN (2, 6, 8)
  AND d.FECHA >= @FechaInicio
  AND d.FECHA <  @FechaFin
  AND d.NULA = 0

ORDER BY origen DESC, dd.NUMOT, d.FECHA;