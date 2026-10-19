# Facturas recibidas por correo (XML de DTE) → pantalla RCV

La casilla **dte@polchile.cl** recibe los DTE (facturas, notas de crédito, guías) que
los proveedores emiten a las empresas del grupo. El workflow `dte-correo-sync.yml`
lee esa casilla por IMAP, parsea cada XML y lo deja en
`shg_dashboards.dte_recibidos` (encabezado, ítems, referencias y el XML completo).
La pantalla **RCV · SII** del Dashboard Finanzas (`dashboard-finanzas-web/rcv.html`
en `GrupoSHG_Systems`) usa esa tabla, a través de la Edge Function `rcv-sii`
(ruta `/dte/folio/<folio>?rut=&tipo=`), para mostrar el detalle de cada factura de
compra y descargar su XML.

```
Gmail dte@polchile.cl ──IMAP──▶ sync_dte_correo.py ──REST──▶ shg_dashboards.dte_recibidos
                                      (cada hora, pg_cron)            │
                                                                      ▼
                     rcv.html  ◀── Edge Function rcv-sii /dte/folio ──┘
```

## Puesta en marcha (una vez)

1. **Gmail.** En la cuenta dte@polchile.cl: activar IMAP (Configuración → Reenvío y
   correo POP/IMAP) y crear una **contraseña de aplicación** (Cuenta de Google →
   Seguridad → Verificación en dos pasos → Contraseñas de aplicaciones). Gmail no
   acepta la clave normal por IMAP. Si el administrador de Workspace tiene bloqueadas
   las contraseñas de aplicación, hay que permitirlas para esa cuenta.
2. **Secretos del repo `GrupoSHG/Scripts`** (`SUPABASE_SERVICE_KEY` ya existe):

   ```bash
   gh secret set DTE_MAIL_USER     -R GrupoSHG/Scripts --body "dte@polchile.cl"
   gh secret set DTE_MAIL_PASSWORD -R GrupoSHG/Scripts   # pega la contraseña de aplicación
   ```

3. **Tabla en Supabase.** Correr `Polchile_Systems/dte_recibidos.sql` en el SQL Editor
   del proyecto `ffxopvzxyeacpbtxuagu` (crea `dte_recibidos`, `dte_correo_cursor`,
   RLS de solo lectura para `authenticated` y la fila del botón "Actualizar datos").
4. **Disparo horario.** Agregar al `automatizacion.programa()` **vivo** (no re-aplicar
   el archivo completo: la cadencia en producción difiere del archivo) este bloque:

   ```sql
   if habil and h between 7 and 20 and mi = 42 then
     perform automatizacion.disparar('dte-correo-sync.yml');
   end if;
   ```

   y en `automatizacion.ultimo_dato()` la rama
   `when 'dte-correo-sync.yml' then (select max(actualizado_en) from shg_dashboards.dte_correo_cursor)`.
5. **Primera carga.** Ejecutar el workflow a mano con `desde_cero = true` y los días
   que se quieran recuperar (90 por defecto):

   ```bash
   gh workflow run dte-correo-sync.yml -R GrupoSHG/Scripts -f desde_cero=true -f dias=180
   ```

Las corridas siguientes solo leen los correos nuevos (cursor por UID en
`dte_correo_cursor`). Si Gmail cambia el `UIDVALIDITY` de la carpeta, el script lo
detecta y vuelve a leer los últimos `DTE_DIAS_INICIAL` días; los duplicados se
resuelven por `(rut_emisor, tipo_dte, folio)`.

## Probar en local

```bash
cd Scripts
# .env con DTE_MAIL_USER, DTE_MAIL_PASSWORD (y SUPABASE_SERVICE_KEY si se quiere escribir)
python3 Polchile_Systems/sync_dte_correo.py --simular --dias 30   # solo lista lo que encontró
python3 Polchile_Systems/sync_dte_correo.py --desde-cero --dias 30
```

Solo usa la librería estándar (imaplib, email, zipfile, xml.etree); `python-dotenv`
es opcional. Toma adjuntos `.xml` y los `.xml` dentro de `.zip`; ignora PDF.

## Qué guarda

Una fila por documento (`Documento`, `Exportaciones` o `Liquidacion`) encontrado en
cada XML, aunque un `EnvioDTE` traiga varios. Columnas principales: `rut_emisor`,
`tipo_dte`, `folio`, fechas, emisor, `rut_receptor` (la empresa del grupo), totales,
`items` (jsonb con `descripcion`, `cantidad`, `unidad`, `precioUnitario`,
`descuento`, `monto`, `codigo`), `referencias` (OC, guías, documentos anulados) y
`xml` (el elemento `DTE` con su firma). `correo_*` guarda de qué correo salió.
