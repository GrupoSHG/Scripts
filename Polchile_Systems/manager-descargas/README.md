# Robot de descargas de Manager → Supabase

Cada hora, de lunes a viernes entre las 9:00 y las 18:00, entra a Manager Time ERP con un navegador sin ventana desde GitHub Actions. Exporta cinco informes y reemplaza estas tablas en Supabase:

| Informe en Manager | Dónde está | Tabla |
|---|---|---|
| Documentos Pendientes, tipo FAV (facturas por cobrar) | Manager → Finanzas → Informes… | `shg_dashboards.documentos_pendientes_fav` |
| 02-INFORME DE VENTAS FULL | Centro de Información | `shg_dashboards.ventas_full` |
| Notas de Venta | Centro de Información | `shg_dashboards.notas_de_venta` |
| \*PRODUCCIÓN\* OP ASOCIADAS A NV POR RANGO FECHA V2 | Centro de Información (acepta el filtro de fechas tal cual) | `shg_dashboards.ordenes_de_produccion` |
| Stock de Productos en Bodegas de Stock | Centro de Información | `stock_productos.stock` (upsert por código y bodega; misma tabla que llena el pipeline diario) |

Esas tablas alimentan el Cockpit, el Calendario, el Dashboard de Producción y las cuentas por cobrar del SSC Cash Report de Finanzas.

## Cómo funciona

1. `robot.py` hace la navegación, calibrada sobre la pantalla real en un viewport de 1600x900:
   - entra a home.ramaflex.cl y presiona "Manager Time ERP", que abre el escritorio remoto TSplus;
   - en el panel Remote App abre "ERP Manager SQL Polchile";
   - en el login de Manager escribe el usuario (`MANAGER_USUARIO`; el combo recuerda al último que entró, y hay varios), confirma que quedó el correcto comparándolo con `referencias/usuario_manager.png` y recién entonces escribe la clave;
   - Documentos Pendientes: Manager → Finanzas → Informes… → Documentos Pendientes; elige FAV en la lista de tipos (el campo no acepta texto), OK, Imprimir → Gestor de Impresión → Exportar, Hoja de Cálculo con "Abrir archivo luego de exportar" marcado → Ejecutar;
   - informes del Centro de Información: Manager → Centro de Información, abre el informe, presiona Guardar (el disquete), escribe el nombre, OK y "¿Abrir con Excel?" Sí;
   - el navegador recibe el `.xls`;
   - al final hace Logoff.
2. En cada paso el robot espera a reconocer la pantalla, comparando una franja con las imágenes de `referencias/`. El escritorio remoto pierde teclas si llegan rápido. Por eso la lista de informes se recorre de a una fila, hasta que la línea "Descripción del Filtro" calza con la referencia del informe.
3. `cargar.py` convierte el `.xls` al formato de la tabla y llama a `shg_dashboards.reemplazar_<tabla>(filas)`. Esa función borra e inserta en una sola transacción, así los dashboards nunca ven datos a medias. Además registra la carga en `shg_dashboards.cargas_manager`.
   - El informe de Ventas Full debe traer, además de las columnas históricas, `NOTA_VENTA` (NV de origen de cada línea) y `FACTURA_REF` (factura referenciada en las notas de crédito). Su SQL es el mismo de `backup-manager/ConsultasSQL/Ventas_Full.sql`; si el informe en Manager aún no las incluye, `cargar.py` avisa y las deja vacías.
   - Si Supabase cancela la función por `statement timeout` (código 57014) o responde 502/503/504, `cargar.py` espera 20 s y reintenta hasta 3 veces. Como el reemplazo es una sola transacción, reintentar no duplica filas. El límite de 8 s que trae el rol de la API se sube para `service_role` con `supabase/timeout_service_role.sql` (se aplica a mano en el SQL Editor).
   - Las tablas se reemplazan una por una: si una falla, el robot igual carga las demás y termina con error indicando cuáles quedaron sin cargar.
4. El monitoreo (`.github/scripts/monitoreo.py`) consulta `ultima_carga_manager()`. Si en horario laboral pasan más de 2 h sin carga, envía un correo.

## Dónde corre

En GitHub Actions: workflow `.github/workflows/manager-descargas.yml`, de lunes a viernes cada hora de 9 a 18 (hora de Santiago). Tiene el botón "Run workflow" para correrlo a mano.

Necesita estos secrets del repo (Settings → Secrets and variables → Actions): `RAMAFLEX_CORREO`, `RAMAFLEX_CLAVE`, `MANAGER_USUARIO`, `MANAGER_CLAVE` y `SUPABASE_SERVICE_KEY`. Si una corrida falla, las capturas de pantalla quedan como artefacto de esa corrida.

Para correrlo en un PC (por ejemplo, para recalibrar):

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium
copy .env.example .env      (completar las credenciales)
```

`ejecutar.bat` deja un log diario en `logs\`, por si se programa en el Programador de tareas de Windows. **No lo dejes corriendo en paralelo con el workflow**: las dos sesiones usan el mismo usuario de Manager y se expulsan una a la otra.

## Uso manual

```
.venv\Scripts\python robot.py               descarga y carga
.venv\Scripts\python robot.py --sin-cargar  solo descarga (a descargas\)
.venv\Scripts\python robot.py --ver         con ventana visible, para ver qué hace
.venv\Scripts\python cargar.py ventas_full descargas\archivo.xls --simular
```

## Si falla

- Revisa la corrida en Actions: el log del paso "Descargar informes" y el artefacto `capturas-...`. Los archivos `error_*.png` muestran la pantalla donde se detuvo.
- **Usa el mismo usuario de Manager que tú.** La URL de TSplus trae `disconnect=1`, así que si tienes Manager abierto cuando corre el robot, una sesión expulsa a la otra. El robot reintenta hasta 4 veces.
- Si se cambia `MANAGER_USUARIO` a otra persona, hay que recapturar `referencias/usuario_manager.png` (el texto del campo Usuario con ese nombre).
- Si Manager cambia de versión o de diseño (posiciones, colores, textos), hay que recalibrar. Las coordenadas están en las constantes al inicio de `robot.py`, y las referencias se recortan de capturas nuevas.
- Para que el robot exporte un informe nuevo del Centro de Información hace falta su referencia `referencias/filtro_<informe>.png` (la franja "Descripción del Filtro" con ese informe seleccionado). La forma rápida de obtenerla sin entrar a Manager: correr el workflow con `calibrar = true` (o `python robot.py --calibrar`); recorre la lista, guarda la franja de cada fila en el artefacto `calibracion-<run_id>` (`fila_NN.png`, más `fila_NN_pantalla.png` para ver cuál es cuál) y basta copiar la del informe buscado con el nombre de la referencia. Luego se agrega la fila a `INFORMES` en `robot.py` y las columnas a `COLUMNAS` en `cargar.py`.
- Si se agrega un informe nuevo al Centro de Información, no pasa nada: el robot busca por nombre, no por posición. Hay tres informes "OP ASOCIADAS A NV POR RANGO FECHA…" que solo difieren en el final del nombre; para la V2 se compara solo ese final (`CAJAS_FILTRO_ESPECIALES`).
- **Ramaflex permite una sola sesión por usuario:** si entras a Ramaflex mientras corre el robot (o el robot entra mientras tú estás), una de las dos sesiones queda invalidada. El robot lo detecta (página en blanco con 401), borra su sesión y vuelve a entrar.
