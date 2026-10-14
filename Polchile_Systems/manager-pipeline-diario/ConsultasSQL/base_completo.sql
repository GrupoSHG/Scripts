
SELECT
    -- Identificación NV / cliente / vendedor
    NV.NUMNOTA                                                          AS [nota_de_venta],
    CONVERT(varchar(10), NV.FECHA, 23)                                  AS [fecha_nv],
    ISNULL(CONVERT(varchar(10), DE.FECHENTR, 23), '')                   AS [fecha_entrega],
    ISNULL(CONVERT(varchar(30), NV.RUTFACT), '')                        AS [rut],
    ISNULL(CL.RAZSOC, '')                                               AS [razon_social],
    LTRIM(RTRIM(ISNULL(PE.NOMBRE,'') + ' ' + ISNULL(PE.APELLIDO,'')))   AS [vendedor],
    CASE WHEN NV.APROBADA = 1 THEN 'Aprobada' ELSE 'Sin Aprobación' END AS [estado_aprobación],

    -- Bodega / ítems
    ISNULL(DE.BODEGA, 0)                                                AS [bodega_id],
    ISNULL(CH.DESCRIP, '')                                              AS [bodega_nombre],
    ISNULL(DE.ITEM, 0)                                                  AS [linea_nv],
    ISNULL(AP.CODIGO, '')                                               AS [codigo_de_producto],
    ISNULL(DE.DESCRIP, '')                                              AS [descripción],
    ISNULL(AP.UNIDAD_COMPRA, '')                                        AS [unidmed],

    -- Cantidades
    CAST(ROUND(DE.CANTIDAD, 3) AS decimal(16,3))                        AS [Q solicitado],
    CAST(ROUND(DE.CANTDESP, 3) AS decimal(16,3))                        AS [Q despachado],
    CAST(ROUND(DE.CANTIDAD - DE.CANTDESP, 3) AS decimal(16,3))          AS [Q por_despachar],

    -- Valor total Ítem
    CAST(ROUND((
          DE.CANTIDAD
        * CASE WHEN NV.MONEDA = '$' THEN 1 ELSE NV.TASACBIO END
        * DE.PRECUNIT
        * (1 - DE.DESCTO/100.0)
        * (1 - CASE WHEN NV.DCTOTIPO = 1
                    THEN NV.DCTOPJE/100.0
                    ELSE NV.DCTOPJE/(NULLIF(NV.TOTNETO,0) + NV.DCTOPJE) END)
    ), 2) AS decimal(16,2))                                             AS [valor_total],

    -- Totales NV
    CAST(ROUND(NV.TOTNETO, 2) AS decimal(16,2))                        AS [total_neto_nv],
    CAST(ROUND(NV.TOTAL , 2) AS decimal(16,2))                         AS [total_nv],
    CAST(ROUND(ISNULL(PAGO.PagadoNV,0), 2) AS decimal(16,2))            AS [pagado_nv],
    CAST(ROUND(NV.TOTAL - ISNULL(PAGO.PagadoNV,0), 2) AS decimal(16,2)) AS [Totpend],

    -- Información de Producción (OP)
    ISNULL(OP.NUM_OP, 0)                                                AS [numero_op],
    ISNULL(CONVERT(varchar(10), OP.FECHACREA, 23), '')                  AS [fecha_creación_op],
    ISNULL(CONVERT(varchar(10), OP.FECHAENT , 23), '')                  AS [fecha_entrega_op],
    ISNULL(CONVERT(varchar(10), OP.FECHAIN  , 23), '')                  AS [inicio_op],
    ISNULL(CONVERT(varchar(10), OP.FECHAFIN , 23), '')                  AS [fecha_termino_op],
    CAST(ROUND(OP.CANTOK , 3) AS decimal(16,3))                         AS [cantidad_en_op],
    CAST(ROUND(OP.CANTPP , 3) AS decimal(16,3))                         AS [produccion_total],
    CASE WHEN ISNULL(OP.CANTPEND, 0) > 0 THEN 'No' ELSE 'Sí' END       AS [termino],
    CAST(ROUND(OP.CANTOK , 3) AS decimal(16,3))                         AS [produccion_terminada],
    CAST(ROUND(OP.CANTPEND, 3) AS decimal(16,3))                        AS [produccion_pendiente],

    -- Estado General
    CASE WHEN DE.CANTDESP < DE.CANTIDAD THEN 'Pendiente' ELSE 'Completada' END AS [estatus_nv],

    -- Información de Compra (OC)
    ISNULL(OC.NUM_OC, 0)                                                AS [num_oc],
    CAST(ROUND(ISNULL(OC.SolicitadoOC, 0), 3) AS decimal(16,3))         AS [solicitado_oc],
    CAST(ROUND(ISNULL(OC.RecibidoOC, 0), 3) AS decimal(16,3))           AS [recibido_oc],
    CASE
        WHEN OC.NUM_OC IS NULL THEN 'Sin OC'
        WHEN OC.SolicitadoOC > OC.RecibidoOC THEN 'OC Abierta'
        ELSE 'OC Cerrada'
    END                                                                 AS [estatus_oc],

    -- Despacho y Facturación
    ISNULL(DG.UltimaGuia, 0)                                            AS [ultima_guia],
    ISNULL(CONVERT(varchar(10), DG.UltimoFechaDespacho, 23), '')        AS [ultimo_fecha_despacho],
    ISNULL(DF.FacturasList, '')                                         AS [facturas_asociadas],
    ISNULL(CONVERT(varchar(10), DF.UltimoFechaFactura, 23), '')         AS [ultimo_fecha_factura],
    CAST(ROUND(ISNULL(DF.PesosFacturados,0), 2) AS decimal(16,2))       AS [pesos_facturados]

FROM NOTV_DB NV
LEFT JOIN NOTDE_DB DE   ON DE.NUMRECOR = NV.NUMREG
LEFT JOIN CLIEN_DB CL   ON NV.NRUTCLIE = CL.NREGUIST
LEFT JOIN ART_DB   AP   ON AP.NREGUIST = DE.NCODART
LEFT JOIN CHOI_DB  CH   ON CH.NUMREG   = DE.BODEGA

-- Subconsulta OP
LEFT JOIN (
    SELECT
        PRP          AS NUMNOTA,
        NCODART,
        MAX(NUMOT)   AS NUM_OP,
        MAX(FECHACREA) AS FECHACREA,
        MAX(FECHAENT)  AS FECHAENT,
        MAX(FECHAIN)   AS FECHAIN,
        MAX(FECHAFIN)  AS FECHAFIN,
        SUM(CANTPP)            AS CANTPP,
        SUM(CANTOK)            AS CANTOK,
        SUM(CANTPP - CANTOK)   AS CANTPEND
    FROM ORDTR_DB
    GROUP BY PRP, NCODART
) OP ON OP.NUMNOTA = NV.NUMNOTA AND OP.NCODART = DE.NCODART

-- Subconsulta OC
LEFT JOIN (
    SELECT
        O.NV,
        D.NCODART,
        MAX(O.NUMOC)        AS NUM_OC,
        SUM(D.CANTIDAD)     AS SolicitadoOC,
        SUM(D.CANTRECI)     AS RecibidoOC
    FROM OC_DB O
    JOIN OCDET_DB D ON D.NUMRECOR = O.NUMREG
    GROUP BY O.NV, D.NCODART
) OC ON OC.NV = NV.NUMREG AND OC.NCODART = DE.NCODART

-- Subconsulta Guías
LEFT JOIN (
    SELECT
        NROPEDIDO AS NUMNOTA,
        MAX(CASE WHEN TIPODOC = 2 THEN NUMFACT END) AS UltimaGuia,
        MAX(CASE WHEN TIPODOC = 2 THEN FECHA   END) AS UltimoFechaDespacho
    FROM DOCU_DB
    GROUP BY NROPEDIDO
) DG ON DG.NUMNOTA = NV.NUMNOTA

-- Subconsulta Facturas
LEFT JOIN (
    SELECT
        d1.NROPEDIDO AS NUMNOTA,
        LEFT(STUFF((
            SELECT ', ' + CAST(f.NUMFACT AS varchar(50))
            FROM (
                SELECT DISTINCT d2.NUMFACT
                FROM DOCU_DB d2
                WHERE d2.NROPEDIDO = d1.NROPEDIDO
                  AND d2.TIPODOC   = 1
                  AND d2.NUMFACT IS NOT NULL
            ) f
            ORDER BY f.NUMFACT
            FOR XML PATH(''), TYPE
        ).value('.', 'nvarchar(max)'), 1, 2, ''), 800) AS FacturasList,
        MAX(CASE WHEN d1.TIPODOC = 1 THEN d1.FECHA END) AS UltimoFechaFactura,
        SUM(CASE WHEN d1.TIPODOC = 1 THEN d1.DEBE  END) AS PesosFacturados
    FROM DOCU_DB d1
    GROUP BY d1.NROPEDIDO
) DF ON DF.NUMNOTA = NV.NUMNOTA

-- Subconsulta Pagos
LEFT JOIN (
    SELECT T6.NUMNOTA, SUM(T7.HABER) AS PagadoNV
    FROM NOTV_DB T6
    LEFT JOIN DOCU_DB T7 ON T7.NUMFACT = T6.NUMNOTA
    WHERE T7.HABER <> 0
      AND T7.TDOCNETEO = 50
    GROUP BY T6.NUMNOTA
) PAGO ON PAGO.NUMNOTA = NV.NUMNOTA

LEFT JOIN PERSO_DB PE ON NV.CODVEND = PE.NUMREG
                      AND ISNULL(PE.VENDEDOR, 0) = 1

WHERE NV.FECHA >= '2025-01-01'
  AND NV.TOTAL <> 0;