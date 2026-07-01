SELECT
    a.CODIGO                                                        AS codigo,
    a.NOMBRE                                                        AS descripcion,
    CAST(ISNULL(sb.stk_fisico,   0) AS DECIMAL(18,4))               AS stk_fisico,
    CAST(ISNULL(pe.por_entregar, 0) AS DECIMAL(18,4))               AS por_entregar,
    CAST(ISNULL(sb.stk_fisico,   0)
       - ISNULL(pe.por_entregar, 0) AS DECIMAL(18,4))               AS disponible,
    CAST(ISNULL(pl.por_llegar,   0) AS DECIMAL(18,4))               AS por_llegar,
    CAST(ISNULL(sb.stk_fisico,   0)
       - ISNULL(pe.por_entregar, 0)
       + ISNULL(pl.por_llegar,   0) AS DECIMAL(18,4))               AS disp_futuro

FROM ART_DB a

INNER JOIN (
    SELECT ARTICULO, SUM(STK_FISICO) AS stk_fisico
    FROM STOCK_DB
    GROUP BY ARTICULO
) sb ON sb.ARTICULO = a.NREGUIST

LEFT JOIN (
    SELECT
        r.NCODART                               AS articulo,
        CAST(SUM((o.CANTPP - o.CANTOK) * r.CANT) AS DECIMAL(18,4)) AS por_entregar
    FROM ORDTR_DB o
        INNER JOIN RECET_DB  r  ON r.IDART     = o.NCODART
        INNER JOIN ART_DB    ac ON ac.NREGUIST = r.NCODART
    WHERE (o.CANTPP - o.CANTOK) > 0
      AND o.TERMINO   = 0
      AND o.EstadoOT <> 2
      AND ac.CODIGO LIKE 'AC%'
    GROUP BY r.NCODART
) pe ON pe.articulo = a.NREGUIST

LEFT JOIN (
    SELECT od.NCODART AS articulo, SUM(od.CANTIDAD - od.CANTRECI) AS por_llegar
    FROM OCDET_DB od
        INNER JOIN OC_DB oc ON oc.NUMREG = od.NUMRECOR
    WHERE (od.CANTIDAD - od.CANTRECI) > 0
    GROUP BY od.NCODART
) pl ON pl.articulo = a.NREGUIST

WHERE a.CODIGO LIKE 'AC%'
  AND (ISNULL(sb.stk_fisico,   0) <> 0
       OR ISNULL(pe.por_entregar, 0) > 0
       OR ISNULL(pl.por_llegar,   0) > 0)

ORDER BY a.CODIGO