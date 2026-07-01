SELECT DISTINCT
    o.PRP                                      AS NOTA_VTA,
    o.NUMOT                                    AS NUM_OP,
    o.FECHACREA,
    o.FECHAENT,
    o.FECHAIN,
    o.INICIADA,
    o.FECHAFIN,
    CAST(o.CANTPP AS DECIMAL(18,6))            AS CANTIDAD_OP,
    a.UNIDAD_COMPRA                            AS UNIDMED,
    CAST(o.CANTOK AS DECIMAL(18,6))            AS CANTIDAD_TERMINADA,
    CAST(o.CANTPP - o.CANTOK AS DECIMAL(18,6)) AS CANTIDAD_PENDIENTE,
    o.NOMBRE                                   AS NOMBRE_OP,
    a.CODIGO                                   AS CODIGO_PRODUCTO,
    a.NOMBRE                                   AS NOMBRE_PRODUCTO,
    a.CLASE1, a.CLASE2, a.CLASE3, a.CLASE4,
    o.BODEGA                                   AS BODEGA_ID_OP,
    ch.DESCRIP                                 AS BODEGA_NOMBRE_OP,
    de.BODEGA                                  AS BODEGA_ID_NV,
    ch2.DESCRIP                                AS BODEGA_NOMBRE_NV

FROM dbo.ORDTR_DB o
JOIN      dbo.ART_DB   a   ON o.NCODART  = a.NREGUIST
LEFT JOIN dbo.CHOI_DB  ch  ON ch.NUMREG  = o.BODEGA
LEFT JOIN dbo.NOTV_DB  nv  ON nv.NUMNOTA = o.PRP
LEFT JOIN dbo.NOTDE_DB de  ON de.NUMRECOR = nv.NUMREG
                          AND de.NCODART = o.NCODART
LEFT JOIN dbo.CHOI_DB  ch2 ON ch2.NUMREG = de.BODEGA

WHERE
    o.FECHACREA >= CONVERT(datetime, '20180101', 112)
AND o.FECHACREA <= CONVERT(datetime, '20301231', 112)

ORDER BY NOTA_VTA, NUM_OP, BODEGA_NOMBRE_NV;       -- ← usar los ALIAS del SELECT