# Edge Function: OCR de facturas

## 1. Instalar Supabase CLI (si no la tienes)

```powershell
npm install -g supabase
```

## 2. Login y link al proyecto

```powershell
supabase login
supabase link --project-ref ffxopvzxyeacpbtxuagu
```

## 3. Conseguir una API key de Google Cloud Vision

1. Ve a [console.cloud.google.com](https://console.cloud.google.com) → crea o selecciona un proyecto.
2. Habilita la **Cloud Vision API** (busca "Vision API" en el buscador de servicios → Enable).
3. Ve a **APIs & Services → Credentials → Create Credentials → API key**.
4. Copia la key generada.

## 4. Configurar los secretos de la función

```powershell
supabase secrets set GOOGLE_VISION_API_KEY=tu-api-key-de-google
```

(`SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` ya están disponibles automáticamente para las Edge Functions, no hace falta configurarlas.)

## 5. Desplegar la función

```powershell
supabase functions deploy procesar-factura
```

Al terminar te va a mostrar la URL de la función, algo como:
```
https://ffxopvzxyeacpbtxuagu.supabase.co/functions/v1/procesar-factura
```

## 6. Conectarla automáticamente (Database Webhook)

Así se dispara sola cada vez que se sube una factura nueva, sin que la app tenga que llamarla directamente:

1. En el dashboard de Supabase: **Database → Webhooks → Create a new hook**.
2. **Name**: `ocr-factura`
3. **Table**: `facturas`
4. **Events**: marca solo **Insert**
5. **Type**: `Supabase Edge Functions`
6. **Edge Function**: selecciona `procesar-factura`
7. Guarda.

Con esto, cada `INSERT` en `facturas` (que la app ya hace al subir la foto) dispara automáticamente el OCR.

## 7. Probar

1. En la app, sube una foto de una factura real.
2. Debería pasar de "Subiendo imagen…" a "Leyendo factura con OCR…" y en unos segundos mostrar proveedor/monto/fecha detectados.
3. Si algo no calza, puedes revisar los logs de la función en **Edge Functions → procesar-factura → Logs** dentro del dashboard de Supabase.

## Notas

- El OCR usa heurísticas simples (busca la palabra "TOTAL" cerca de un número, la primera línea con letras como proveedor, y un patrón de fecha dd/mm/aaaa). No va a ser perfecto con todas las boletas — por eso la app siempre te deja revisar/corregir antes de confirmar el gasto.
- Si una factura queda en estado `error` (Vision no devolvió texto, por ejemplo foto borrosa), la app te deja reintentar con otra foto.
