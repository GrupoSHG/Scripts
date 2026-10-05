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
    CAST(ROUND(DD.CANTIDAD, 3) AS decimal(16,3))                        AS [cantidad_despachada],

    -- Precio de LISTA/CATÁLOGO del producto (ART_DB)
    CAST(ISNULL(AP.PRECVTA, 0) AS decimal(16,2))                        AS [precio_producto],

    -- Precio UNITARIO real de esta línea (DOCDE_DB)
    DD.PRECUNIT                                                         AS [precio_unitario],

    -- Total de la línea
    CAST(ROUND(DD.CANTIDAD * DD.PRECUNIT, 2) AS decimal(16,2))          AS [total_linea],

    -- FACTURA asociada a la misma Nota de Venta.
    -- OJO: TIPODOC 0 y 1 no se pudieron distinguir con certeza (ver
    -- diagnóstico previo) — se incluyen ambos por seguridad. Si una NV
    -- tiene más de una factura, esto puede DUPLICAR filas de la guía;
    -- revisar en la práctica si pasa, y si hace falta agregar una
    -- condición extra para quedarse con una sola.
    FAC.NUMFACT                                                         AS [factura_asociada],
    CONVERT(varchar(10), FAC.FECHA, 23)                                 AS [fecha_factura],

    -- TODAS las Notas de Crédito asociadas a la misma Nota de Venta
    -- (TIPODOC = 4, confirmado), agrupadas para no duplicar la fila de
    -- la guía si hay más de una NC.
    ISNULL(NC.numeros_nc, '')                                           AS [notas_credito],
    ISNULL(NC.cantidad_nc, 0)                                           AS [cantidad_notas_credito],
    ISNULL(NC.monto_total_nc, 0)                                        AS [monto_total_notas_credito]

FROM NOTV_DB NV
LEFT JOIN CLIEN_DB  CL  ON CL.NREGUIST = NV.NRUTCLIE
LEFT JOIN PERSO_DB  PE  ON PE.NUMREG   = NV.CODVEND AND ISNULL(PE.VENDEDOR, 0) = 1
JOIN      DOCU_DB   D   ON D.NROPEDIDO = NV.NUMNOTA AND D.TIPODOC = 2
JOIN      DOCDE_DB  DD  ON DD.NUMRECOR = D.NUMREG
LEFT JOIN ART_DB    AP  ON AP.NREGUIST = DD.NCODART
LEFT JOIN DOCU_DB   FAC ON FAC.NROPEDIDO = NV.NUMNOTA AND FAC.TIPODOC IN (0, 1)
LEFT JOIN (
    SELECT
        NROPEDIDO,
        STRING_AGG(CAST(NUMFACT AS VARCHAR(20)), ', ') AS numeros_nc,
        COUNT(*)                                        AS cantidad_nc,
        SUM(TOTAL)                                       AS monto_total_nc
    FROM DOCU_DB
    WHERE TIPODOC = 4
    GROUP BY NROPEDIDO
) NC ON NC.NROPEDIDO = NV.NUMNOTA

WHERE NV.FECHA >= '2026-01-01'
  AND NV.TOTAL <> 0

ORDER BY NV.NUMNOTA, D.NUMFACT, DD.ITEM;
