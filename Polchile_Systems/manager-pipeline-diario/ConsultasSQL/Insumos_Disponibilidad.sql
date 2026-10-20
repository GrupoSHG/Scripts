-- ============================================================================
-- Insumos_Disponibilidad.sql — stock y OC por llegar de cada material
-- ============================================================================
-- Una fila por artículo que es componente de alguna receta o que tiene una
-- línea de OC con saldo por recibir. Alimenta shg_dashboards.insumos_disponibilidad
-- (la crea el cargador masivo del pipeline diario), que supabase/compras_diarias.sql
-- cruza con Necesidades_Materiales.sql.
--
-- Stock: STOCK_DB separado en planta (bodegas TRINIDAD R) y Los Paltos, sin
-- merma ni segunda selección. Por llegar: CANTIDAD - CANTRECI > 0, el mismo
-- criterio de Consumos_acero.sql e Importaciones.sql.
-- ============================================================================

WITH receta AS (
    SELECT r.IDART, r.NCODART
    FROM RECET_DB r
    WHERE r.NCODART <> 0 AND r.CANT > 0
),
stock AS (
    SELECT
        s.ARTICULO,
        SUM(CASE WHEN ch.DESCRIP LIKE 'TRINIDAD%' THEN s.STK_FISICO ELSE 0 END) AS stk_planta,
        SUM(CASE WHEN ch.DESCRIP LIKE 'LOS PALTOS%' THEN s.STK_FISICO ELSE 0 END) AS stk_los_paltos,
        SUM(s.STK_FISICO)                                                       AS stk_total
    FROM STOCK_DB s
        LEFT JOIN CHOI_DB ch ON ch.NUMREG = s.COD_BODEG
    WHERE ISNULL(ch.DESCRIP, '') NOT LIKE '%MERMA%'
      AND ISNULL(ch.DESCRIP, '') NOT LIKE '%SEGUNDA%'
    GROUP BY s.ARTICULO
),
por_llegar AS (
    SELECT
        od.NCODART                                         AS articulo,
        SUM(od.CANTIDAD - ISNULL(od.CANTRECI, 0))          AS por_llegar,
        MIN(CAST(ISNULL(od.FECHENTR, oc.FECHAENT) AS DATE)) AS proxima_llegada,
        COUNT(DISTINCT oc.NUMOC)                           AS oc_pendientes
    FROM OCDET_DB od
        INNER JOIN OC_DB oc ON oc.NUMREG = od.NUMRECOR
    WHERE od.CANTIDAD - ISNULL(od.CANTRECI, 0) > 0
    GROUP BY od.NCODART
),
-- Lista "OC (proveedor)" de las OC con saldo, igual que proveedor_por_llegar
-- de Consumos_acero.sql
oc_lista AS (
    SELECT x.articulo,
           LEFT(STUFF((
               SELECT ', ' + CAST(oc2.NUMOC AS varchar(20)) + ' ('
                      + LTRIM(RTRIM(ISNULL(cli.RAZSOC, 'sin proveedor'))) + ')'
               FROM (SELECT DISTINCT od2.NUMRECOR
                     FROM OCDET_DB od2
                     WHERE od2.NCODART = x.articulo
                       AND od2.CANTIDAD - ISNULL(od2.CANTRECI, 0) > 0) d
                   INNER JOIN OC_DB oc2 ON oc2.NUMREG = d.NUMRECOR
                   LEFT JOIN CLIEN_DB cli ON cli.NREGUIST = oc2.NRUTPROV
               ORDER BY oc2.NUMOC
               FOR XML PATH(''), TYPE
           ).value('.', 'nvarchar(max)'), 1, 2, ''), 500) AS oc_detalle
    FROM por_llegar x
),
articulos AS (
    SELECT NCODART AS articulo FROM receta
    UNION
    SELECT articulo FROM por_llegar
)
SELECT
    LTRIM(RTRIM(a.CODIGO))                                    AS codigo,
    LTRIM(RTRIM(a.NOMBRE))                                    AS nombre,
    a.UNIDMED                                                 AS unidad,
    CASE
        WHEN a.CODIGO LIKE 'PSA%'                                     THEN 'Bandeja'
        WHEN a.CODIGO LIKE 'AC%' AND a.CODIGO NOT LIKE 'ACC%'         THEN 'Acero'
        WHEN a.CODIGO LIKE 'PD%' OR a.CODIGO LIKE 'POL%'
             AND a.CODIGO NOT LIKE 'POLIOL%'                          THEN 'Poliestireno'
        WHEN a.CODIGO LIKE 'ISO%' OR a.CODIGO LIKE 'POLIOL%'          THEN 'Químicos'
        ELSE 'Otro'
    END                                                       AS familia,
    CASE WHEN a.NREGUIST IN (SELECT IDART FROM receta) THEN 0 ELSE 1 END AS es_comprado,
    CAST(ISNULL(s.stk_planta, 0)     AS DECIMAL(18,4))        AS stk_planta,
    CAST(ISNULL(s.stk_los_paltos, 0) AS DECIMAL(18,4))        AS stk_los_paltos,
    CAST(ISNULL(s.stk_total, 0)      AS DECIMAL(18,4))        AS stk_total,
    CAST(ISNULL(p.por_llegar, 0)     AS DECIMAL(18,4))        AS por_llegar,
    ISNULL(p.oc_pendientes, 0)                                AS oc_pendientes,
    ISNULL(CONVERT(varchar(10), p.proxima_llegada, 23), '')   AS proxima_llegada,
    ISNULL(l.oc_detalle, '')                                  AS oc_detalle,
    CAST(ISNULL(a.PULTCOM, 0) AS DECIMAL(18,4))               AS precio_ultima_compra
FROM articulos x
    INNER JOIN ART_DB a ON a.NREGUIST = x.articulo
    LEFT JOIN stock s       ON s.ARTICULO = x.articulo
    LEFT JOIN por_llegar p  ON p.articulo = x.articulo
    LEFT JOIN oc_lista l    ON l.articulo = x.articulo
ORDER BY familia, codigo;
