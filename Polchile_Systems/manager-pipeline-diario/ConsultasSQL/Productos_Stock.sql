SELECT 
    ch.CODIGO                               AS bodega,
    ch.DESCRIP                              AS bodega_nombre,
    a.CODIGO                                AS codigo,
    a.NOMBRE                                AS nombre,
    a.UNIDAD_COMPRA                         AS unidmed,
    CAST(s.STK_FISICO AS DECIMAL(18,2))     AS stk_fisico
FROM STOCK_DB s
    INNER JOIN ART_DB  a  ON s.ARTICULO  = a.NREGUIST
    INNER JOIN CHOI_DB ch ON s.COD_BODEG = ch.NUMREG
WHERE s.STK_FISICO <> 0
  AND ch.CODIGO IN ('B291', 'B191')   -- 🔹 ambas bodegas
ORDER BY ch.CODIGO, a.CODIGO;