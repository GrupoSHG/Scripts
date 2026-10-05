SELECT 
    d.NUMFACT       AS Documento,
    CASE WHEN d.ESELECTR = 1 THEN 'E-FAV' ELSE 'FAV' END AS doc_cod,
    d.RUTFACT       AS Rut,
    c.RAZSOC        AS RazonSocial,
    d.FECHA         AS Fecha,
    d.VENCIMIE      AS Vmto,
    d.DEBE          AS Debe,
    d.HABER         AS Haber,
    d.DEBE - d.HABER AS Saldo
FROM DOCU_DB d
LEFT JOIN CLIEN_DB c ON d.RUTFACT = c.RUT
WHERE d.CTA = 50492
  AND d.TIPODOC = 0
  AND d.FECHA >= '2026-01-01'
  AND d.DEBE - d.HABER > 0
ORDER BY d.FECHA