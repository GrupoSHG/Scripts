DECLARE @FechaInicio DATE = '2026-06-01';
DECLARE @FechaFin    DATE = '2026-07-01';

SELECT DISTINCT
    od.CENTCC                              AS ctocosto,
    oc.NUMOC                               AS numoc,
    oc.NUMREG                              AS numreg,
    od.ITEM                                AS item,                  -- ← AGREGADO
    oc.RUTPROV                             AS rutprov,
    cli.RAZSOC                             AS nombre_proveedor,
    oc.IVA                                 AS iva,
    oc.FECHA                               AS fecha,
    oc.TASAREF                             AS tasacbio,
    oc.NRUTPROV                            AS nrutprov,
    oc.TOTNETO                             AS totneto,
    oc.DCTOPJE                             AS dctopje,
    oc.DCTOTIPO                            AS dctotipo,
    od.CENTCC                              AS centcc,
    od.CANTIDAD                            AS cantidad,
    oc.NUMEMPOC                            AS numempdo,
    art.NIVEL1                             AS nivel1,
    art.NIVEL2                             AS nivel2,
    art.NIVEL3                             AS nivel3,
    art.NIVEL4                             AS nivel4,
    art.NIVEL5                             AS nivel5,
    art.NIVEL6                             AS nivel6,
    art.NIVEL7                             AS nivel7,
    art.NIVEL8                             AS nivel8,
    art.NIVEL9                             AS nivel9,
    art.UNIDMED                            AS unidmed,
    art.PRECVTA                            AS precvta,
    od.DESCRIP                             AS nombre,
    art.CLASE1                             AS clase1,
    art.CLASE2                             AS clase2,
    art.CODIGO                             AS codigo,
    (od.CANTIDAD * od.PRECUNIT)            AS total,
    art.COSTOREP                           AS costo,
    art.VALPROM                            AS precioponderado,
    art.COSTOREP                           AS costoreposicion,
    od.PRECUNIT                            AS preciounitario

FROM OC_DB oc
    INNER JOIN OCDET_DB od  ON oc.NUMREG   = od.NUMRECOR
    LEFT  JOIN ART_DB   art ON od.NCODART  = art.NREGUIST
    LEFT  JOIN CLIEN_DB cli ON oc.NRUTPROV = cli.NREGUIST

WHERE oc.FECHA >= @FechaInicio
  AND oc.FECHA <  @FechaFin

ORDER BY oc.FECHA, oc.NUMOC, od.ITEM;