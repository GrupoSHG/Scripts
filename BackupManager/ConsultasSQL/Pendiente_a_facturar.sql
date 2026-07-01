SELECT DISTINCT
    -- Identificación NV / cliente / vendedor
    NV.NUMNOTA                                                          AS [nota_de_venta],
    CONVERT(varchar(10), NV.FECHA, 23)                                  AS [fecha_nv],
    ISNULL(CONVERT(varchar(30), NV.RUTFACT), '')                        AS [rut],
    ISNULL(CL.RAZSOC, '')                                               AS [razon_social],
    LTRIM(RTRIM(ISNULL(PE.NOMBRE,'') + ' ' + ISNULL(PE.APELLIDO,'')))   AS [vendedor],
    CASE WHEN NV.APROBADA = 1 THEN 'Aprobada' ELSE 'Sin Aprobación' END AS [estado_aprobación],

    -- Totales de la NV (Convertidos a números enteros limpios sin decimales)
    CAST(ROUND(ISNULL(NV.TOTAL,0), 0) AS BIGINT)                        AS [total_nv],
    CAST(ROUND(ISNULL(PAGO.PagadoNV,0), 0) AS BIGINT)                   AS [pagado_nv],
    CAST(ROUND(ISNULL(NV.TOTAL,0) - ISNULL(PAGO.PagadoNV,0), 0) AS BIGINT) AS [Totpend]

FROM NOTV_DB NV
LEFT JOIN CLIEN_DB CL ON NV.NRUTCLIE = CL.NREGUIST
LEFT JOIN PERSO_DB PE ON NV.CODVEND  = PE.NUMREG AND ISNULL(PE.VENDEDOR,0) = 1

-- Pagos netados a la NV
LEFT JOIN (
    SELECT T6.NUMNOTA, SUM(ISNULL(T7.HABER,0)) AS PagadoNV
    FROM NOTV_DB T6
    LEFT JOIN DOCU_DB T7 ON T7.NUMFACT = T6.NUMNOTA
    WHERE T7.HABER <> 0 AND T7.TDOCNETEO = 50
    GROUP BY T6.NUMNOTA
) PAGO ON PAGO.NUMNOTA = NV.NUMNOTA

WHERE NV.FECHA >= '2026-01-01'
  AND NV.TOTAL <> 0
  AND (ISNULL(NV.TOTAL,0) - ISNULL(PAGO.PagadoNV,0)) > 0

ORDER BY NV.FECHA DESC, NV.NUMNOTA;