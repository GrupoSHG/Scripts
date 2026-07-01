SELECT DISTINCT
    NV.NUMNOTA                                                          AS [nota_de_venta],
    
    -- Fechas individuales originales
    ISNULL(CONVERT(varchar(10), PEND.FechaEntregaMin, 23), '')         AS [fecha_entrega_original_lineas],
    ISNULL(CONVERT(varchar(10), ATR.fecha_ultima, 23), '')             AS [fecha_entrega_modificada],
    
    -- Fecha entrega final (la mayor entre original y modificada)
    CONVERT(varchar(10), 
        CASE 
            WHEN ATR.fecha_ultima >= PEND.FechaEntregaMin THEN ATR.fecha_ultima
            ELSE ISNULL(PEND.FechaEntregaMin, ATR.fecha_ultima)
        END, 23)                                                        AS [fecha_entrega_final],

    -- Días de modificación
    CASE 
        WHEN ATR.fecha_ultima IS NOT NULL AND PEND.FechaEntregaMin IS NOT NULL
        THEN DATEDIFF(DAY, PEND.FechaEntregaMin, ATR.fecha_ultima)
        ELSE 0
    END                                                                 AS [dias_modificacion_vs_original],
    
    -- Cantidad de cambios REALES (solo modificaciones, sin contar la original)
    ISNULL(ATR.cantidad_cambios, 0)                                     AS [cantidad_cambios_fecha_entrega],
    
    -- Cantidades
    CAST(ROUND(PEND.TotalSolicitado, 3) AS decimal(16,3))               AS [q_solicitado],
    CAST(ROUND(PEND.TotalPorDespachar, 3) AS decimal(16,3))             AS [q_por_despachar],
   
    ISNULL(CL.RAZSOC, '')                                               AS [cliente],
    CASE WHEN NV.APROBADA = 1 THEN 'Aprobada' ELSE 'Sin Aprobación' END AS [estado],
    
    -- Montos
    CAST(ROUND(NV.TOTAL  , 0) AS BIGINT)                                AS [total_nv],
    CAST(ROUND(NV.TOTNETO, 0) AS BIGINT)                                AS [total_neto_nv],
    CAST(ROUND(ISNULL(DF.PesosFacturados,0), 0) AS BIGINT)              AS [pesos_facturados],
    CAST(ROUND(NV.TOTAL - ISNULL(DF.PesosFacturados,0), 0) AS BIGINT)   AS [pesos_por_facturar],
    CAST(ROUND(ISNULL(PAGO.PagadoNV,0), 0) AS BIGINT)                   AS [pagado_nv],
    CAST(ROUND(NV.TOTAL - ISNULL(PAGO.PagadoNV,0), 0) AS BIGINT)        AS [total_pendiente_de_cobro],
    
    -- Montos despacho (proporcional)
    CAST(ROUND(
        CASE WHEN PEND.TotalSolicitado > 0 
             THEN NV.TOTNETO * ((PEND.TotalSolicitado - PEND.TotalPorDespachar) / PEND.TotalSolicitado)
             ELSE 0 END, 0) AS BIGINT)                                  AS [total_entregado_pesos],
    
    CAST(ROUND(
        CASE WHEN PEND.TotalSolicitado > 0 
             THEN NV.TOTNETO * (PEND.TotalPorDespachar / PEND.TotalSolicitado)
             ELSE 0 END, 0) AS BIGINT)                                  AS [total_por_entregar_pesos]

FROM NOTV_DB NV
LEFT JOIN CLIEN_DB CL ON NV.NRUTCLIE = CL.NREGUIST

-- Pendientes consolidados por NV
INNER JOIN (
    SELECT
        DE.NUMRECOR,
        SUM(DE.CANTIDAD)               AS TotalSolicitado,
        SUM(DE.CANTIDAD - DE.CANTDESP) AS TotalPorDespachar,
        MIN(DE.FECHENTR)               AS FechaEntregaMin
    FROM NOTDE_DB DE
    WHERE (DE.CANTIDAD - DE.CANTDESP) > 0
    GROUP BY DE.NUMRECOR
) PEND ON PEND.NUMRECOR = NV.NUMREG

-- Atributos fecha de entrega (CLASE_DB TABLA 137) — Opción B: solo modificaciones
LEFT JOIN (
    SELECT
        C.NCLIE,
        v.d1   AS fecha_inicial,
        (SELECT MAX(f) FROM (VALUES (v.d1),(v.d2),(v.d3),(v.d4),(v.d5)) AS t(f)) AS fecha_ultima,
        
        -- OPCIÓN B: cantidad de fechas distintas - 1 (no cuenta la original)
        CASE 
            WHEN (SELECT COUNT(DISTINCT f) 
                  FROM (VALUES (v.d1),(v.d2),(v.d3),(v.d4),(v.d5)) AS t(f)
                  WHERE f IS NOT NULL) > 0
            THEN (SELECT COUNT(DISTINCT f) 
                  FROM (VALUES (v.d1),(v.d2),(v.d3),(v.d4),(v.d5)) AS t(f)
                  WHERE f IS NOT NULL) - 1
            ELSE 0
        END AS cantidad_cambios
        
    FROM CLASE_DB C
    CROSS APPLY (
        SELECT
            TRY_CONVERT(date, LEFT(LTRIM(C.ATB1),10), 105) AS d1,
            TRY_CONVERT(date, LEFT(LTRIM(C.ATB2),10), 105) AS d2,
            TRY_CONVERT(date, LEFT(LTRIM(C.ATB3),10), 105) AS d3,
            TRY_CONVERT(date, LEFT(LTRIM(C.ATB4),10), 105) AS d4,
            TRY_CONVERT(date, LEFT(LTRIM(C.ATB5),10), 105) AS d5
    ) v
    WHERE C.TABLA = '137'
) ATR ON ATR.NCLIE = NV.NUMREG

-- Pesos facturados por NV
LEFT JOIN (
    SELECT d1.NROPEDIDO AS NUMNOTA,
        SUM(CASE WHEN d1.TIPODOC=1 THEN d1.DEBE END) AS PesosFacturados
    FROM DOCU_DB d1
    GROUP BY d1.NROPEDIDO
) DF ON DF.NUMNOTA = NV.NUMNOTA

-- Pagos reales por NV
LEFT JOIN (
    SELECT T6.NUMNOTA, SUM(T7.HABER) AS PagadoNV
    FROM NOTV_DB T6
    LEFT JOIN DOCU_DB T7 ON T7.NUMFACT = T6.NUMNOTA
    WHERE T7.HABER <> 0 AND T7.TDOCNETEO = 50
    GROUP BY T6.NUMNOTA
) PAGO ON PAGO.NUMNOTA = NV.NUMNOTA

WHERE NV.FECHA >= '2025-01-01'
  AND NV.TOTAL <> 0

ORDER BY [fecha_entrega_original_lineas] ASC;