# Notas sobre la API de Mercado Público (verificado contra respuestas reales)

La documentación oficial tiene errores en algunos códigos de estado; aquí queda lo observado.

## Errores y autenticación (2026-10-16)

- Un ticket inválido **no** devuelve 401: responde **HTTP 203** con
  `{"Codigo":203,"Mensaje":"Ticket no válido."}` (UTF-8). `mp_api.py` trata todo lo que no sea
  200 como error; solo reintenta 429 y 5xx.

## Códigos de estado de licitación

Pendiente: se completa con la primera respuesta real (`CodigoEstado` / `Estado` del listado y del detalle).
