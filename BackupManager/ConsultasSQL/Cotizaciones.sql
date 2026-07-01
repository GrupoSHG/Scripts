
SELECT 
    CAST(cot.NUMCOT AS INT)                 AS documento_nro,
    CONVERT(varchar(10), cot.FECHA, 103)    AS fecha,
    cli.RAZSOC                              AS senores,
    cot.PROBABI                             AS probabilidad,
    pe.CODIGO                               AS vendedor,
    cot.MONEDA                              AS moneda,
    CAST(cot.TOTNETO AS DECIMAL(18,0))      AS total

FROM COTI_DB cot
    LEFT JOIN CLIEN_DB cli ON cot.NRUTCLIE = cli.NREGUIST
    LEFT JOIN PERSO_DB pe  ON cot.CODVEND  = pe.NUMREG

WHERE cot.FECHA >= '2026-01-01'
  AND cot.TOTNETO <> 0

ORDER BY cot.NUMCOT DESC;