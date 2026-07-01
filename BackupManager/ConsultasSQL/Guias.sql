SELECT
    NV.NUMNOTA                                                          AS [nota_de_venta],
    CONVERT(varchar(10), NV.FECHA, 23)                                  AS [fecha_nv],
    ISNULL(CL.RAZSOC, '')                                               AS [razon_social],
    LTRIM(RTRIM(ISNULL(PE.NOMBRE,'') + ' ' + ISNULL(PE.APELLIDO,'')))   AS [vendedor],
    D.NUMFACT                                                           AS [guia_despacho],
    CONVERT(varchar(10), D.FECHA, 23)                                   AS [fecha_guia],
    ISNULL(AP.CODIGO, '')                                               AS [codigo_producto],
    ISNULL(DD.DESCRIP, '')                                              AS [descripcion],
    ISNULL(AP.CLASE1, '')                                               AS [clase_1],
    ISNULL(AP.CLASE2, '')                                               AS [clase_2],
    CAST(ROUND(DD.CANTIDAD, 3) AS decimal(16,3))                        AS [cantidad_despachada]

FROM NOTV_DB NV
LEFT JOIN CLIEN_DB  CL  ON CL.NREGUIST = NV.NRUTCLIE
LEFT JOIN PERSO_DB  PE  ON PE.NUMREG   = NV.CODVEND AND ISNULL(PE.VENDEDOR, 0) = 1
JOIN      DOCU_DB   D   ON D.NROPEDIDO = NV.NUMNOTA AND D.TIPODOC = 2
JOIN      DOCDE_DB  DD  ON DD.NUMRECOR = D.NUMREG
LEFT JOIN ART_DB    AP  ON AP.NREGUIST = DD.NCODART

WHERE NV.FECHA >= '2025-01-01'
  AND NV.TOTAL <> 0

ORDER BY NV.NUMNOTA, D.NUMFACT, DD.ITEM