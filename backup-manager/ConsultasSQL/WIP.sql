SELECT 
    a.CLASE2                                       AS clase2,
    CASE 
        WHEN ch.DESCRIP LIKE '%INSUMOS%'              THEN 'INSUMOS'
        WHEN ch.DESCRIP LIKE '%PRODUCTOS TERMINADOS%' THEN 'TERMINADO'
        ELSE 'OTRO'
    END                                            AS tipo,
    a.UNIDAD_COMPRA                                AS unidmed,
    CAST(SUM(o.CANTPP - o.CANTOK) AS DECIMAL(18,2)) AS pendiente_fabricar

FROM dbo.ORDTR_DB o
JOIN      dbo.ART_DB  a  ON o.NCODART = a.NREGUIST
LEFT JOIN dbo.CHOI_DB ch ON ch.NUMREG = o.BODEGA

WHERE (o.CANTPP - o.CANTOK) > 0
  AND (ch.DESCRIP LIKE '%INSUMOS%' OR ch.DESCRIP LIKE '%PRODUCTOS TERMINADOS%')

GROUP BY 
    a.CLASE2,
    CASE 
        WHEN ch.DESCRIP LIKE '%INSUMOS%'              THEN 'INSUMOS'
        WHEN ch.DESCRIP LIKE '%PRODUCTOS TERMINADOS%' THEN 'TERMINADO'
        ELSE 'OTRO'
    END,
    a.UNIDAD_COMPRA

ORDER BY tipo, clase2, unidmed;