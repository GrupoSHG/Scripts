SELECT DISTINCT
    a.CODIGO                                       AS codigo,
    a.NOMBRE                                       AS nombre,
    CAST(l.STK_LOTE AS DECIMAL(18,2))              AS stk_lote,
    l.NUMOT                                        AS numot,
    a.CLASE4                                       AS clase4,
    a.CLASE3                                       AS clase3,
    a.CLASE2                                       AS clase2,
    a.CLASE1                                       AS clase1,
    a.UNIDAD_COMPRA                                AS unidad,
    ch.DESCRIP                                     AS bodega,
    l.NUMREGLOT                                    AS num_lote

FROM LOTES_DB l
    INNER JOIN ART_DB  a  ON l.ARTICULO  = a.NREGUIST
    LEFT  JOIN CHOI_DB ch ON l.COD_BODEG = ch.NUMREG

WHERE a.CLASE1 = 'Insumo Acero'
  AND l.STK_LOTE > 0                               -- solo lotes con stock
  AND l.NUMOT IS NOT NULL                          -- omite nulos
  AND LTRIM(RTRIM(l.NUMOT)) <> ''                  -- omite vacíos

ORDER BY a.CODIGO, l.NUMOT;