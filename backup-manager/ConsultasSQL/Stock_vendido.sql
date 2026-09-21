SELECT 
    NV.NUMNOTA                                          AS nota_de_venta,
    ISNULL(DE.BODEGA, 0)                                AS bodega_id,
    ISNULL(CH.DESCRIP, '')                              AS bodega_nombre,
    ISNULL(AP.CODIGO, '')                               AS codigo_de_producto,
    ISNULL(DE.DESCRIP, '')                              AS descripcion,
    ISNULL(AP.UNIDAD_COMPRA, '')                        AS unidmed,
    CAST(ROUND(DE.CANTIDAD, 3) AS decimal(16,3))        AS q_solicitado,
    CAST(ROUND((
          DE.CANTIDAD
        * CASE WHEN NV.MONEDA = '$' THEN 1 ELSE NV.TASACBIO END
        * DE.PRECUNIT
        * (1 - DE.DESCTO/100.0)
        * (1 - CASE WHEN NV.DCTOTIPO = 1
                    THEN NV.DCTOPJE/100.0
                    ELSE NV.DCTOPJE/(NULLIF(NV.TOTNETO,0) + NV.DCTOPJE) END)
    ), 2) AS decimal(16,2))                             AS valor_total,
    NV.NUMNOTA                                          AS nota_de_venta,
    CONVERT(varchar(10), NV.FECHA, 23)                  AS fecha_nv

FROM NOTV_DB NV
    LEFT JOIN NOTDE_DB DE ON DE.NUMRECOR = NV.NUMREG
    LEFT JOIN ART_DB   AP ON AP.NREGUIST = DE.NCODART
    LEFT JOIN CHOI_DB  CH ON CH.NUMREG   = DE.BODEGA

WHERE NV.FECHA >= '2025-01-01'
  AND NV.TOTAL <> 0
  AND AP.CODIGO LIKE '%STK%'
  AND CH.DESCRIP LIKE '%TERMINAD%'

ORDER BY NV.NUMNOTA;