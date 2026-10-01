# Robot de descargas de Manager → Supabase

Cada hora, de lunes a viernes entre las 9:00 y las 18:00, entra a Manager Time ERP con un navegador sin ventana desde GitHub Actions. Exporta dos informes del Centro de Información y reemplaza estas tablas en Supabase:

| Informe en Manager | Tabla |
|---|---|
| 02-INFORME DE VENTAS FULL | `shg_dashboards.ventas_full` |
| Notas de Venta | `shg_dashboards.notas_de_venta` |

Esas tablas alimentan el Cockpit, el Calendario y el Dashboard de Producción.

## Cómo funciona

1. `robot.py` hace la navegación, calibrada sobre la pantalla real en un viewport de 1600x900:
   - entra a home.ramaflex.cl y presiona "Manager Time ERP", que abre el escritorio remoto TSplus;
   - en el panel Remote App abre "ERP Manager SQL Polchile";
   - en el login de Manager escribe la clave;
   - va a Manager → Centro de Información, abre el informe, presiona Guardar (el disquete), escribe el nombre, OK y "¿Abrir con Excel?" Sí;
   - el navegador recibe el `.xls`;
   - al final hace Logoff.
2. En cada paso el robot espera a reconocer la pantalla, comparando una franja con las imágenes de `referencias/`. El escritorio remoto pierde teclas si llegan rápido. Por eso la lista de informes se recorre de a una fila, hasta que la línea "Descripción del Filtro" calza con la referencia del informe.
3. `cargar.py` convierte el `.xls` al formato de la tabla y llama a `shg_dashboards.reemplazar_<tabla>(filas)`. Esa función borra e inserta en una sola transacción, así los dashboards nunca ven datos a medias. Además registra la carga en `shg_dashboards.cargas_manager`.
4. El monitoreo (`.github/scripts/monitoreo.py`) consulta `ultima_carga_manager()`. Si en horario laboral pasan más de 2 h sin carga, envía un correo.

## Dónde corre

En GitHub Actions: workflow `.github/workflows/manager-descargas.yml`, de lunes a viernes cada hora de 9 a 18 (hora de Santiago). Tiene el botón "Run workflow" para correrlo a mano.

Necesita estos secrets del repo (Settings → Secrets and variables → Actions): `RAMAFLEX_CORREO`, `RAMAFLEX_CLAVE`, `MANAGER_CLAVE` y `SUPABASE_SERVICE_KEY`. Si una corrida falla, las capturas de pantalla quedan como artefacto de esa corrida.

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
- Si Manager cambia de versión o de diseño (posiciones, colores, textos), hay que recalibrar. Las coordenadas están en las constantes al inicio de `robot.py`, y las referencias se recortan de capturas nuevas.
- Si se agrega un informe nuevo al Centro de Información, no pasa nada: el robot busca por nombre, no por posición.
