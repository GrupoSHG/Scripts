-- ============================================================================
-- Necesidades_Materiales.sql — materiales que pide cada NV y cada OP abierta
-- ============================================================================
-- Una fila por (origen, NV, OP, producto, componente). Alimenta la tabla
-- shg_dashboards.necesidades_materiales (la crea el cargador masivo del
-- pipeline diario: la hoja del Excel se llama igual que este archivo), que
-- las vistas de supabase/compras_diarias.sql cruzan con el stock y las OC por
-- llegar (Insumos_Disponibilidad.sql) para sacar "qué comprar hoy" y qué NV
-- tienen todo el material para liberarse.
--
-- Receta: RECET_DB (IDART = producto, NCODART = componente, CANT por unidad).
-- Los artículos comprados (acero, ISO, poliol, planchas PD...) tienen filas
-- de relleno con NCODART = 0 y CANT = 0: solo cuentan las filas con
-- NCODART <> 0 y CANT > 0. Un componente "fabricado" es el que tiene receta
-- real (p. ej. la bandeja PSA dentro del panel PA); los demás se compran.
--
-- Origen 'OP': OP abiertas (TERMINO = 0, EstadoOT <> 2, pendiente > 0). Se
--   desarman hasta los comprados, pero sin bajar de las bandejas PSA: esas
--   tienen sus propias OP, que aparecen aquí con su acero. Las filas de PSA
--   pedidas por una OP de panel son el insumo del WIP de bandejas.
-- Origen 'NV': líneas de NV con saldo por despachar y SIN OP para ese
--   producto. Se desarman hasta los comprados (todos los niveles), porque
--   todavía no existe ninguna OP intermedia.
-- Los fabricados intermedios (PSA, acero cortado AC1065 desde AC1219...)
-- quedan también como filas, con es_comprado = 0.
-- No descuenta stock de productos intermedios (bandejas ya hechas): la cuenta
-- es conservadora.
-- ============================================================================

DECLARE @FechaInicio DATE = '2025-01-01';

WITH receta AS (
    SELECT r.IDART, r.NCODART, CAST(r.CANT AS DECIMAL(18,6)) AS cant
    FROM RECET_DB r
    WHERE r.NCODART <> 0 AND r.CANT > 0
),
fabricados AS (
    SELECT DISTINCT IDART FROM receta
),
bandejas AS (
    SELECT NREGUIST FROM ART_DB WHERE CODIGO LIKE 'PSA%'
),
-- Saldo por producir de cada OP abierta y saldo por despachar de las líneas
-- de NV fabricadas que aún no tienen OP
pedidos AS (
    SELECT
        'OP'                                    AS origen,
        o.PRP                                   AS nota_vta,
        o.NUMOT                                 AS num_op,
        o.NCODART                               AS producto,
        CAST(o.FECHAENT AS DATE)                AS fecha_entrega,
        CAST(o.CANTPP - o.CANTOK AS DECIMAL(18,6)) AS cantidad
    FROM ORDTR_DB o
    WHERE o.TERMINO = 0
      AND o.EstadoOT <> 2
      AND o.CANTPP - o.CANTOK > 0
    UNION ALL
    SELECT
        'NV',
        nv.NUMNOTA,
        0,
        de.NCODART,
        CAST(ISNULL(de.FECHENTR, nv.FECHA) AS DATE) AS fecha_entrega,
        CAST(SUM(de.CANTIDAD - de.CANTDESP) AS DECIMAL(18,6)) AS cantidad
    FROM NOTV_DB nv
        INNER JOIN NOTDE_DB de ON de.NUMRECOR = nv.NUMREG
    WHERE nv.FECHA >= @FechaInicio
      AND nv.TOTAL <> 0
      AND de.CANTIDAD - de.CANTDESP > 0
      AND de.NCODART IN (SELECT IDART FROM fabricados)
      AND NOT EXISTS (SELECT 1 FROM ORDTR_DB o
                      WHERE o.PRP = nv.NUMNOTA AND o.NCODART = de.NCODART)
    GROUP BY nv.NUMNOTA, de.NCODART, CAST(ISNULL(de.FECHENTR, nv.FECHA) AS DATE)
),
-- Explosión recursiva (nivel 1 = componente directo)
filas AS (
    SELECT p.origen, p.nota_vta, p.num_op, p.producto, p.fecha_entrega,
           p.cantidad AS cantidad_producto, r.IDART AS padre, r.NCODART AS componente,
           1 AS nivel, CAST(p.cantidad * r.cant AS DECIMAL(18,6)) AS cantidad
    FROM pedidos p
        INNER JOIN receta r ON r.IDART = p.producto
    UNION ALL
    SELECT f.origen, f.nota_vta, f.num_op, f.producto, f.fecha_entrega,
           f.cantidad_producto, r.IDART, r.NCODART,
           f.nivel + 1, CAST(f.cantidad * r.cant AS DECIMAL(18,6))
    FROM filas f
        INNER JOIN receta r ON r.IDART = f.componente
    WHERE f.nivel < 6
      AND NOT (f.origen = 'OP' AND f.componente IN (SELECT NREGUIST FROM bandejas))
)
SELECT
    f.origen,
    f.nota_vta,
    f.num_op,
    ISNULL(CONVERT(varchar(10), f.fecha_entrega, 23), '') AS fecha_entrega,
    LTRIM(RTRIM(ap.CODIGO))                     AS codigo_producto,
    LTRIM(RTRIM(ap.NOMBRE))                     AS nombre_producto,
    CAST(f.cantidad_producto AS DECIMAL(18,4))  AS cantidad_producto,
    ap.UNIDMED                                  AS unidad_producto,
    f.nivel,
    LTRIM(RTRIM(apa.CODIGO))                    AS codigo_padre,
    LTRIM(RTRIM(ac.CODIGO))                     AS codigo_componente,
    LTRIM(RTRIM(ac.NOMBRE))                     AS nombre_componente,
    ac.UNIDMED                                  AS unidad_componente,
    CASE WHEN f.componente IN (SELECT IDART FROM fabricados) THEN 0 ELSE 1 END AS es_comprado,
    CAST(SUM(f.cantidad) AS DECIMAL(18,4))      AS cantidad_requerida
FROM filas f
    INNER JOIN ART_DB ap  ON ap.NREGUIST  = f.producto
    INNER JOIN ART_DB apa ON apa.NREGUIST = f.padre
    INNER JOIN ART_DB ac  ON ac.NREGUIST  = f.componente
GROUP BY f.origen, f.nota_vta, f.num_op, f.fecha_entrega, ap.CODIGO, ap.NOMBRE,
         f.cantidad_producto, ap.UNIDMED, f.nivel, apa.CODIGO, ac.CODIGO, ac.NOMBRE,
         ac.UNIDMED, f.componente
ORDER BY f.fecha_entrega, f.nota_vta, f.num_op, f.nivel, ac.CODIGO
OPTION (MAXRECURSION 10);
