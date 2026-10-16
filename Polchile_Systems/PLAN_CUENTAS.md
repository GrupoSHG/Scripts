# Plan de cuentas contables → pantalla RCV (cuenta por código de artículo)

En el detalle de una factura de compra (pantalla **RCV · SII** del Dashboard Finanzas),
finanzas asigna a cada ítem un **código** de artículo y una **cuenta contable** antes de
cargarla a Manager. Para que no haya que escribirlas a mano cada vez:

- `shg_dashboards.plan_cuentas` guarda el plan de cuentas de cada empresa. La pantalla
  lo usa para autocompletar la cuenta (por código o por nombre).
- `shg_dashboards.codigos_cuenta` guarda qué cuenta corresponde a cada código de
  artículo. Se llena solo: cada vez que alguien completa código + cuenta en la pantalla,
  la Edge Function `rcv-sii` (`POST /cuenta-contable`) lo memoriza, y la próxima factura
  con ese código trae la cuenta puesta.

```
Excel/CSV del plan ──cargar_plan_cuentas.py──▶ plan_cuentas ──▶ rcv-sii /cuentas-contables ──▶ autocompletar
finanzas digita código + cuenta ──▶ rcv-sii POST /cuenta-contable ──▶ codigos_cuenta ──▶ /cuenta-contable/<código>
```

## Cargar o actualizar el plan

1. Aplicar `Polchile_Systems/plan_cuentas.sql` en el SQL Editor (una vez; es idempotente).
2. Exportar el plan de cuentas desde Manager (Contabilidad → Plan de cuentas → exportar) a
   Excel o CSV. Sirve cualquier archivo con una columna de código y una de nombre; si trae
   tipo, nivel o "imputable" también se cargan.
3. Cargar:

   ```bash
   cd Scripts
   pip install openpyxl xlrd          # solo la primera vez (xlrd para .xls)
   python3 Polchile_Systems/cargar_plan_cuentas.py "plan_cuentas.xlsx" --simular     # revisa qué leyó
   python3 Polchile_Systems/cargar_plan_cuentas.py "plan_cuentas.xlsx"               # carga (upsert)
   python3 Polchile_Systems/cargar_plan_cuentas.py "plan_m5.xlsx" --empresa m5
   ```

   Necesita `SUPABASE_SERVICE_KEY` en `.env`. Volver a cargar actualiza nombres y agrega
   cuentas nuevas; con `--desactivar-faltantes` además marca `activo=false` las que ya no
   vienen en el archivo.

El "Plan de Cuentas Manager.xlsx" (Drive) trae el plan en la primera hoja, columnas `q_cod`
y `q_nom`, con la jerarquía en la sangría del nombre y un listado de facturas en las columnas
de al lado (se ignora). El cargador infiere nivel y tipo desde el código de 6 dígitos (raíz
`x00000`, grupo `xx0000`, subgrupo `xxxx00`, cuenta imputable el resto) y marca como
agrupación las que terminan en `00`. Cargado el 16/10/2026: 313 cuentas, 220 imputables.
Excepción: `420900 COMISION POR MEDIOS DE PAGO` termina en `00` pero Manager la usa como
cuenta de compra de artículos; se dejó imputable a mano
(`update shg_dashboards.plan_cuentas set imputable = true where codigo in (select cuenta from shg_dashboards.codigos_cuenta)`).

## Cargar el calce código de artículo → cuenta desde Manager

Manager exporta por artículo sus cuentas (compra `art_ctacom`, venta `art_ctavta`, costo
`art_ctacto`, más centros de costo y datos libres). Ese archivo (6.641 artículos en oct-2026,
cuenta de compra `110804` Existencias en el 97 %, cuentas de gasto `4105xx`/`4205xx` en los
códigos `G0xx`) se carga con:

```bash
python3 Polchile_Systems/cargar_codigos_cuenta.py "articulos_cuentas.xlsx" --simular
python3 Polchile_Systems/cargar_codigos_cuenta.py "articulos_cuentas.xlsx"
```

Las filas con cuenta de compra `0` se saltan. Cada carga actualiza los códigos que ya existen
(la última carga gana sobre lo asignado desde la pantalla), así que conviene corregir en Manager
y volver a exportar en vez de corregir solo en Supabase.

## Corregir un calce código → cuenta

Basta con volver a asignar la cuenta en la pantalla: la última asignación gana. Para
revisarlos o editarlos en bloque, la tabla `shg_dashboards.codigos_cuenta` es editable
en el Table Editor de Supabase (`empresa`, `codigo_item`, `cuenta`).
