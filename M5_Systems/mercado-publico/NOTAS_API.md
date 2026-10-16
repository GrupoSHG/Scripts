# Notas sobre la API de Mercado Público (verificado contra respuestas reales)

La documentación oficial tiene errores en algunos códigos de estado; aquí queda lo observado.

## Errores y autenticación (2026-10-16)

- Un ticket inválido **no** devuelve 401: responde **HTTP 203** con
  `{"Codigo":203,"Mensaje":"Ticket no válido."}` (UTF-8). `mp_api.py` trata todo lo que no sea
  200 como error; solo reintenta 429 y 5xx.

## Códigos de estado de licitación

- `licitaciones.json?estado=activas` (2026-10-16): 4.839 licitaciones, **todas con `CodigoEstado` = 5**
  (Publicada). El listado trae solo `CodigoExterno`, `Nombre`, `CodigoEstado` y `FechaCierre`;
  organismo, montos y descripción requieren el detalle (`?codigo=`), una solicitud por licitación.
- La respuesta trae `Cantidad`, `FechaCreacion` (UTC), `Version` y `Listado`.
- Pendiente para la etapa 2: verificar el resto de códigos (cerrada, desierta, adjudicada, revocada,
  suspendida) con el listado por fecha, que incluye todos los estados.
