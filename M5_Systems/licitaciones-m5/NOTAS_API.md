# Notas sobre la API de Mercado Público

La documentación oficial (https://www.chilecompra.cl/api/) tiene errores en algunos códigos de
estado. Aquí queda lo observado en respuestas reales. Lo marcado "por confirmar" se cierra con la
primera corrida de este repositorio (`salida/estados_vistos.json` y `salida/AAAA-MM-DD/embudo.json`).

## Errores, autenticación y límites

Verificado el 2026-10-16 con el job anterior (`GrupoSHG/Scripts`, `M5_Systems/mercado-publico/`):

- Un ticket inválido **no** devuelve 401: responde **HTTP 203** con
  `{"Codigo":203,"Mensaje":"Ticket no válido."}`. Este cliente lo trata como error fatal.
- Con 0,4 s entre llamadas la API respondió **HTTP 429** a cerca de la mitad de los detalles; con
  1,5 s (`ajustes.yaml`) no. Cada reintento cuenta como una solicitud para el límite diario.
- Desde GitHub Actions (IP de centro de datos, runner `ubuntu-latest`) la API respondió 200 en todas
  las corridas del 16 al 18/10/2026. No se ha visto un **403**; si aparece, el proceso corta sin
  reintentar e indica que puede ser un bloqueo de IP.
- El error 10500 ("peticiones simultáneas") llega con HTTP 200 y cuerpo `{"Codigo":10500,...}`
  según la documentación: se reintenta como un 429. **Por confirmar** en una respuesta real.

## Códigos de estado de licitación

| Código | Estado (texto del detalle) | Documentación | Visto |
|---|---|---|---|
| 5 | Publicada | 5 | listado `estado=activas` y detalle |
| 6 | Cerrada | 6 | listado por fecha |
| 7 | Desierta | 7 | listado por fecha |
| 8 | Adjudicada | 8 | listado por fecha |
| 15 | **Revocada** | dice **18** | detalle de 1305504-10-LP26 |
| 16 | Suspendida | dice **19** | listado por fecha; texto **por confirmar** en un detalle |

## Forma de las respuestas

- Listado (`fecha=` o `estado=`): `Cantidad`, `FechaCreacion` (UTC), `Version`, `Listado`; cada ítem
  trae solo `CodigoExterno`, `Nombre`, `CodigoEstado`, `FechaCierre`.
- **`fecha=ddmmaaaa` no es "publicadas ese día"**: trae las licitaciones con algún movimiento en
  esa fecha, en cualquier estado (el 15/10/2026: 1.355). Por eso se filtra por estado.
- Detalle (`codigo=`): organismo y región en `Comprador`, fechas en `Fechas` (hora local de Chile
  sin zona; `1900-01-02` = vacío), `MontoEstimado` con `VisibilidadMonto` (1 = publicado), ítems en
  `Items.Listado` con categoría UNSPSC (`72…` = servicios de construcción).
- El detalle trae nombres, correos y teléfonos de funcionarios: el proceso guarda solo los campos de
  la lista blanca de `licitaciones/detalle.py`.
- **Adjuntos y bases: por confirmar** con `python -m licitaciones detalle <código>`.
