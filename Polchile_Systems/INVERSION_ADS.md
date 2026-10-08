# Inversión en Ads → Cockpit Comercial y dashboard CRM

Lleva el gasto diario de Google Ads (y, a mano, el de Meta Ads) a Supabase para que la pestaña
**CRM Polchile** del Cockpit y el dashboard CRM Comercial muestren inversión, costo por lead y
retorno, cruzados con los leads que el CRM ya marca como pagados (`fuente = "google ads"`,
`fuente_sesion = "Paid Search"`, etc.).

```
Google Ads ──(script diario 06:00)──▶ hoja de Google ──(ads-polchile-sync.yml 07:40)──▶ polchile_crm.inversion_ads
                                      pestaña "google"                                          │
                                      pestaña "meta" (a mano)                                   ▼
                                                                         polchile_crm.resumen_dashboard → Cockpit / dashboard CRM
```

Se eligió un **script de Google Ads** y no la API porque la API exige un token de desarrollador
(cuenta administradora, solicitud a Google y días de espera); el script corre dentro de la cuenta
con los permisos del usuario que lo autoriza y solo escribe una hoja, así ninguna clave queda en
Google Ads.

## Archivos

| Archivo | Qué es |
|---|---|
| `Polchile_Systems/google_ads_script.js` | Script que se pega en Google Ads. Escribe la pestaña `google` (gasto diario por campaña, últimos `DIAS` días) y una pestaña `estado`. |
| `Polchile_Systems/sync_ads_polchile.py` | Lee la hoja (pestañas `google` y `meta`) y llama al RPC `polchile_crm.cargar_inversion_ads`. |
| `Polchile_Systems/inversion_ads.sql` | Tabla `polchile_crm.inversion_ads` (RLS: lectura con sesión) y el RPC de carga (solo `service_role`). |
| `.github/workflows/ads-polchile-sync.yml` | Workflow diario; lo dispara `automatizacion.programa()` a las 07:40. |
| `GrupoSHG_Systems/Polchile_Systems/comercial-crm/resumen_dashboard.sql` | Agrega la clave `ads` al resumen: inversión, leads pagados, CPL, NV atribuidas, retorno, por mes y por campaña. |

## Instalación (una sola vez)

1. **Hoja de Google.** *Hecho el 08-10-2026:* la hoja "Inversión Ads Polchile"
   (`docs.google.com/spreadsheets/d/18RH7f65V080ChSQUJYgmYeJmg-mYdG0OwI2sCj6SVv0`, en el Drive de
   atorres@polchile.cl) está compartida como *Lector* con la cuenta de servicio del pipeline
   (`bot-erp@polchile.iam.gserviceaccount.com`, la de `GOOGLE_CREDENTIALS_JSON`) y su id quedó en la
   variable `ADS_POLCHILE_HOJA` del repo. Si algún día se reemplaza la hoja:

   ```
   gh variable set ADS_POLCHILE_HOJA -R GrupoSHG/Scripts --body "<ID>"
   ```

2. **Script en Google Ads.** En la cuenta de Polchile: Herramientas → Acciones masivas →
   Secuencias de comandos → **+**. Pegar `google_ads_script.js` (ya trae el `HOJA_ID`), dejar
   `DIAS = 400` para la primera carga, **Autorizar**, *Vista previa* y luego *Ejecutar*. Revisar que
   la pestaña `google` quedó con filas y la pestaña `estado` dice `moneda CLP`. Después cambiar a
   `DIAS = 60`, guardar y programarlo **Diario a las 06:00**.
   - Si al autorizar la cuenta es una cuenta administradora (MCC), crear el script dentro de la
     cuenta cliente de Polchile, no en la administradora.
   - Google ajusta el gasto de los últimos días; por eso cada corrida reescribe la ventana completa
     y el RPC reemplaza esas fechas en Supabase sin borrar la historia anterior.

3. **SQL en Supabase** (SQL Editor, en este orden):
   1. `Scripts/Polchile_Systems/inversion_ads.sql`
   2. `GrupoSHG_Systems/Polchile_Systems/comercial-crm/resumen_dashboard.sql`
   3. La línea nueva de `automatizacion.programa()` (`ads-polchile-sync.yml` a las 07:40). El
      archivo `automatizacion/disparador_workflows.sql` quedó igualado a la función viva el
      08-10-2026, así que se puede volver a correr entero; igual conviene comparar antes con
      `select prosrc from pg_proc where proname = 'programa'`.

4. **Primera carga y verificación.**

   ```
   gh workflow run ads-polchile-sync.yml -R GrupoSHG/Scripts
   gh run list -R GrupoSHG/Scripts --workflow ads-polchile-sync.yml -L 1
   ```

   ```sql
   select plataforma, min(fecha), max(fecha), count(*) filas, sum(costo) costo
   from polchile_crm.inversion_ads group by 1;
   ```

   En el Cockpit (pestaña CRM Polchile) aparece la sección **Inversión en Ads**; mientras la tabla
   esté vacía la sección lo dice.

## Meta Ads (opcional, a mano)

Agregar una pestaña `meta` a la misma hoja con el encabezado
`fecha | campana_id | campana | costo | impresiones | clics | conversiones` (solo `fecha` y
`costo` son obligatorias; una fila por día o por mes, con la fecha del primer día) y el workflow
la carga igual. Si más adelante se conecta la Meta Marketing API, basta con que escriba esa pestaña.

## Cómo se calculan los indicadores (`resumen_dashboard`, clave `ads`)

- **Inversión**: suma de `costo` de `inversion_ads` con `fecha` dentro del período, por plataforma.
- **Leads pagados**: oportunidades del pipeline "Oportunidades / Cot" creadas en el período cuya
  plataforma resuelve `polchile_crm.plataforma_ads(fuente, fuente_sesion, medio, campana)`:
  Google = `fuente` "google ads"/"gads…", `fuente_sesion` "Paid Search", `medio` cpc/ppc o campaña
  "gads…"; Meta = `fuente` "meta ads"/"meta form"/"facebook…", `fuente_sesion` "Paid Social".
- **Costo por lead (CPL)**: inversión ÷ leads pagados.
- **NV atribuidas / vendido**: NV ganadas del pipeline "Vendido" en el período cuya propia fuente es
  pagada o cuyo contacto llegó por un lead pagado (cualquier fecha).
- **Retorno (ROAS)**: vendido atribuido ÷ inversión; también se muestra la diferencia en CLP.
- **Por campaña**: inversión, clics y conversiones de la plataforma, más los leads del CRM cuya
  `campana` coincide con el nombre de la campaña (normalizado); si GHL no guarda el nombre igual,
  esa columna queda en 0 y la fila sigue sirviendo para la inversión.

Limitaciones conocidas: solo la mitad de las NV del pipeline "Vendido" comparte contacto con una
oportunidad del pipeline comercial, así que el vendido atribuido es un piso, no un techo; y las
conversiones de Google Ads no son leads del CRM (cuentan clics en WhatsApp, formularios, etc.).

## Probar en local

```
pip install google-api-python-client google-auth
# .env junto al script: GOOGLE_CREDENTIALS_JSON={...}, SUPABASE_SERVICE_KEY=..., ADS_POLCHILE_HOJA=...
python Polchile_Systems/sync_ads_polchile.py --simular
```
