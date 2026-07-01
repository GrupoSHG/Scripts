SELECT 
    n.NUMREG                                AS numreg,
    n.NUMNOTA                               AS numnota,
    CONVERT(varchar(10), n.FECHA, 103)      AS fecha,
    n.NRUTCLIE                              AS nrutclie,
    n.NRUTFACT                              AS nrutfact,
    n.RUTFACT                               AS rutfact,
    p.CODIGO                                AS codvend,
    p.NOMBRE                                AS nom_vddor,
    p.APELLIDO                              AS apell_vddor,
    n.MONEDA                                AS moneda,
    n.DCTOPJE                               AS dctopje,
    CAST(n.TOTNETO AS DECIMAL(18,0))        AS totneto,
    n.DCTOTIPO                              AS dctotipo,
    n.DCTOPESO                              AS dctopeso,
    n.TASACBIO                              AS tasacbio

FROM NOTV_DB n
LEFT JOIN PERSO_DB p ON p.NUMREG = n.CODVEND

WHERE n.FECHA >= '2026-01-01'
  AND n.TOTAL <> 0

ORDER BY n.NUMNOTA;