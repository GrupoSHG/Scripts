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

## Corregir un calce código → cuenta

Basta con volver a asignar la cuenta en la pantalla: la última asignación gana. Para
revisarlos o editarlos en bloque, la tabla `shg_dashboards.codigos_cuenta` es editable
en el Table Editor de Supabase (`empresa`, `codigo_item`, `cuenta`).
