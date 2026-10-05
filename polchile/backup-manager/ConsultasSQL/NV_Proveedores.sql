SELECT
    c.NREGUIST  AS id_manager,
    c.RAZSOC    AS nombre,
    c.RUT       AS rut,
    c.DIR       AS direccion,
    c.CIUDAD    AS ciudad,
    c.COMUNA    AS comuna,
    c.FONO      AS telefono,
    c.EMAIL     AS email
FROM CLIEN_DB c
WHERE c.TIPO IN (2, 3)
  AND c.IMPUTABLE = 1
ORDER BY c.NREGUIST DESC;