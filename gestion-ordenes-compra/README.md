# OC Polchile

App web para gestión y control de Órdenes de Compra (OC) asociadas a Notas de Venta (NV), con flujo de autorización por PIN.

## Stack
- Single-file HTML/JS (sin build step) — mismo patrón que HEA
- Supabase (DB + Auth vía PIN propio, sin Supabase Auth)
- Proyecto Supabase: **Grupo SHG Dashboards** (`hauricnpsamnwyhondse`)

## Estructura
```
oc-polchile/
├── index.html    # app completa (login, nueva OC, control de autorización)
├── schema.sql    # schema de Supabase (correr una sola vez en SQL Editor)
└── README.md
```

## Setup inicial
1. Crear proyecto en supabase.com (ya hecho: Grupo SHG Dashboards)
2. SQL Editor → correr `schema.sql` completo
3. Reemplazar el usuario admin de ejemplo (PIN `1234`) por los PINs reales del equipo:
   ```sql
   update usuarios set pin = 'XXXX', nombre = 'Nombre Real' where pin = '1234';
   -- o insertar más usuarios:
   insert into usuarios (nombre, pin, rol) values ('Nombre', 'PIN', 'user'); -- o 'admin'
   ```
4. Abrir `index.html` (local o desplegado) y probar login

## Deploy
Pendiente de definir: Firebase Hosting (como HEA/Despachos) u otro. Si es Firebase:
```
firebase init hosting   # (una sola vez, seleccionar/crear proyecto)
firebase deploy --only hosting
```

## Modelo de datos (resumen)
- `usuarios` — login por PIN, rol admin/user
- `proveedores` + `proveedor_contactos` — se crean al vuelo desde la app (marcha blanca)
- `nvs` — Notas de Venta, con `monto_neto` y `umbral_pct` (variable por NV)
- `ocs` + `oc_items` — Órdenes de Compra, total autocalculado por trigger
- Vista `v_control_autorizacion` — para reportes agregados por NV

## Flujo
1. Crear NV (pestaña "NVs") con su monto neto y umbral %
2. Crear OC asociada a esa NV (pestaña "Nueva OC") — cualquier usuario
3. Admin revisa en "Control" y aprueba/revoca desde el celular
