# Notas sobre la API de Mercado Público

La documentación oficial (https://www.chilecompra.cl/api/) tiene errores en algunos códigos de
estado. Aquí queda lo observado en respuestas reales. Cada corrida va sumando a
`salida/estados_vistos.json` los pares código → texto que aparecen en los detalles.

## Errores, autenticación y límites

- Un ticket inválido **no** devuelve 401: responde **HTTP 203** con
  `{"Codigo":203,"Mensaje":"Ticket no válido."}` (visto el 16/10/2026). Este cliente lo trata como
  error fatal.
- **HTTP 429**: con 0,4 s entre llamadas llegó a cerca de la mitad de los detalles (16/10). Con 1,5 s
  (`ajustes.yaml`) igual aparece de vez en cuando: el 19/10 hubo 2 de 13 solicitudes con 429 en el
  primer intento, y las dos se recuperaron en el primer reintento. En una tanda de 20 detalles
  seguidos (19/10, 12:44, de día) fueron **12 de 33**: casi una de cada dos solicitudes. Todas se
  recuperaron al primer reintento, pero cada reintento cuenta para el límite diario, así que la pausa
  quedó en **3 s**.
- Desde GitHub Actions (IP de centro de datos, runner `ubuntu-latest`) la API respondió en todas las
  corridas del job anterior del 16 al 18/10/2026. No se ha visto un **403**; si aparece, el proceso
  corta sin reintentar e indica que puede ser un bloqueo de IP.
- El error 10500 ("peticiones simultáneas") llega, según la documentación, con HTTP 200 y cuerpo
  `{"Codigo":10500,...}`: se reintenta como un 429. Aún no visto en una respuesta real.

## Códigos de estado de licitación

Confirmados contra el detalle (`Estado` / `CodigoEstado`) el 19/10/2026, salvo 6 y 8, vistos solo
en listados:

| Código | Texto que devuelve el detalle | Documentación | Licitación de ejemplo |
|---|---|---|---|
| 5 | Publicada | 5 | 4174-34-LP26 |
| 6 | Cerrada | 6 | (listado) |
| 7 | Desierta (o art. 3 ó 9 Ley 19.886) | 7 | 1057973-1-LR26 |
| 8 | Adjudicada | 8 | (listado) |
| 15 | **Revocada** | dice **18** | 761391-73-LE26 |
| 16 | **Suspendida** | dice **19** | 2355-23-LE26 |

## Forma de las respuestas

- Listado (`fecha=` o `estado=`): `Cantidad`, `FechaCreacion` (UTC), `Version`, `Listado`; cada ítem
  trae solo `CodigoExterno`, `Nombre`, `CodigoEstado`, `FechaCierre`.
- **`fecha=ddmmaaaa` no es "publicadas ese día"**: trae las licitaciones con algún movimiento en
  esa fecha, en cualquier estado (el 15/10/2026, un miércoles: 1.355; el 18-19/10, fin de semana y
  mañana del lunes: 296). Por eso se filtra por estado.
- Detalle (`codigo=`): organismo y región en `Comprador`; fechas en `Fechas` (hora local de Chile
  sin zona; `1900-01-02` = vacío). **`FechaCierre` de primer nivel viene `null` en el detalle**: la
  fecha real está en `Fechas.FechaCierre`. `MontoEstimado` con `VisibilidadMonto` (1 = publicado),
  `FuenteFinanciamiento`, `SubContratacion`, ítems en `Items.Listado` con categoría UNSPSC
  (`72…` = servicios de construcción).
- `Descripcion` tiene como máximo 500 caracteres; en las 7 licitaciones vistas el 19/10 midió
  entre 62 y 500.
- El detalle trae nombres, correos y teléfonos de funcionarios (`NombreResponsablePago`,
  `EmailResponsableContrato`, `FonoResponsableContrato`, `Comprador.NombreUsuario`, ...): el proceso
  guarda solo los campos de la lista blanca de `licitaciones/detalle.py`.

## Adjuntos y bases: la API NO los entrega

Verificado con 4174-34-LP26 el 19/10/2026: el detalle no tiene ningún campo de adjuntos, documentos,
URLs ni bases (`EsBaseTipo` solo indica si usa bases tipo). Las bases administrativas y técnicas,
los anexos, las garantías exigidas y los registros (MOP, MINVU) están solo en la ficha web
(`DetailsAcquisition.aspx?idlicitacion=<código>`). Para la evaluación eso significa que el detalle
alcanza para clasificar (tipo de obra, organismo, región, monto, plazos, financiamiento), pero no
para verificar requisitos, garantías ni registros: esos campos salen `null` y la licitación se
marca para revisar las bases a mano.

## Órdenes de compra (`ordenesdecompra.json`), para precios de referencia (26/10/2026)

Prueba con `python -m licitaciones precios-oc --fecha 22102026 --max 50`:

- El listado por fecha trae solo `Codigo`, `CodigoEstado` y `Nombre` (17.762 órdenes el 22/10/2026).
  Estados vistos en el detalle: 4 "Enviada a proveedor", 5 "En proceso", 6 "Aceptada",
  12 "Recepción Conforme"; el 9 (cancelada según la documentación) se excluye.
- Cada ítem trae `Producto`, `CodigoProducto`, `CodigoCategoria` (UNSPSC), `EspecificacionComprador`,
  `EspecificacionProveedor`, `Cantidad`, `Unidad`, `Moneda`, `PrecioNeto`, `Total`.
- **`PrecioNeto` es por unidad y sin IVA**: `Total = Cantidad x PrecioNeto` en 133 de 133 ítems con total.
- **`Unidad` viene siempre vacía** (0 de 258): la unidad y la presentación están en el texto de la
  especificación ("SACO", "PLANCHA", "BOLSA 100 UNIDADES"); solo 75 de 258 la dicen explícitamente.
- **`Producto` suele estar mal clasificado por el comprador** ("Saco de cemento" como "Cementos
  disolventes", "Gravilla" como "Esparcidoras de gravilla"): no sirve para agrupar precios.
- El detalle trae nombre, cargo, teléfono y correo de los contactos del comprador y del proveedor, y el
  nombre y RUT del proveedor (puede ser persona natural): `precios_oc.sanitizar` no guarda ninguno.
