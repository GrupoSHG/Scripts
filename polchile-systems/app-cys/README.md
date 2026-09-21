# App Sotito — Centros de Costo

## Setup

1. `npm install`
2. Crea un proyecto en [Supabase](https://supabase.com) y corre `supabase_schema.sql` en el SQL Editor.
3. Crea el bucket de Storage `facturas` (público, o con política de lectura firmada).
4. Copia `.env.example` a `.env` y completa `VITE_SUPABASE_URL` y `VITE_SUPABASE_ANON_KEY`.
5. `npm run dev` para probar localmente.

## Deploy en Netlify

1. Sube este repo a GitHub.
2. En Netlify: "Add new site" → "Import an existing project" → selecciona el repo.
3. Build command: `npm run build` — Publish directory: `dist` (ya configurado en `netlify.toml`).
4. Agrega las variables de entorno `VITE_SUPABASE_URL` y `VITE_SUPABASE_ANON_KEY` en Netlify → Site settings → Environment variables.
5. Deploy.

## Pendiente

- Edge Function de Supabase para el OCR (Google Cloud Vision) que procese las facturas subidas y actualice `estado_ocr` a `leida`, dejando `proveedor`, `monto` y `fecha` listos para confirmar.
- Sistema de roles (Superadmin/Admin/Usuario) vía Supabase Auth + tabla `usuarios_roles`.
