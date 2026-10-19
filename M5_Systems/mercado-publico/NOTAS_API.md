# Notas sobre la API de Mercado Público (verificado contra respuestas reales)

La documentación oficial tiene errores en algunos códigos de estado; aquí queda lo observado.

## Errores, autenticación y límites (2026-10-16)

- Un ticket inválido **no** devuelve 401: responde **HTTP 203** con
  `{"Codigo":203,"Mensaje":"Ticket no válido."}` (UTF-8). `mp_api.py` trata todo lo que no sea
  200 como error; solo reintenta 429 y 5xx.
- Con 0,4 s entre llamadas la API respondió **HTTP 429** a cerca de la mitad de los detalles
  (los reintentos los recuperaron). La pausa quedó en 1,5 s (`config.json`). Cada reintento cuenta
  como una solicitud para el límite diario.

## Códigos de estado de licitación

| Código | Estado (texto que devuelve el detalle) | Visto |
|---|---|---|
| 5 | Publicada | listado `estado=activas` (4.839, todas 5) y detalle |
| 6 | Cerrada | listado por fecha |
| 7 | Desierta | listado por fecha |
| 8 | Adjudicada | listado por fecha |
| 15 | **Revocada** | detalle de 1305504-10-LP26. La documentación dice 18. |
| 16 | Suspendida (según documentación, que dice 19) | listado por fecha; texto por confirmar en un detalle |

`descarga_diaria.py` guarda en `salida/estados_vistos.json` cada par código → texto que aparece
en los detalles, para ir confirmando la tabla.

## Forma de las respuestas

- Listados (`estado=` o `fecha=`): `Cantidad`, `FechaCreacion` (UTC), `Version`, `Listado`; cada
  ítem trae solo `CodigoExterno`, `Nombre`, `CodigoEstado`, `FechaCierre`.
- **`fecha=ddmmaaaa` no es "publicadas ese día"**: trae las licitaciones con algún movimiento en
  esa fecha, en cualquier estado (el 15/10/2026: 1.355, con estados 5, 6, 7, 8, 15 y 16; una
  publicada en junio aparecía por su revocación). Por eso el proceso filtra por estado y toma la
  fecha de publicación del detalle.
- Detalle (`codigo=`): organismo y región en `Comprador`, fechas en `Fechas` (hora local de Chile,
  sin zona; `1900-01-02` = vacío), `MontoEstimado` con `VisibilidadMonto` (1 = publicado), ítems en
  `Items.Listado` con categoría UNSPSC (`72…` = servicios de construcción).
- El detalle trae nombres de funcionarios (`NombreResponsablePago`, `NombreResponsableContrato`,
  `Comprador.NombreUsuario`, ...): **no se guardan**.
