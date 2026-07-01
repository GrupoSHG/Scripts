# CONFIGURAR ACCESO A GOOGLE DRIVE (solo una vez)
# =====================================================
# Sigue estos pasos para que el script pueda subir
# archivos a tu Google Drive automáticamente.

## PASO 1 — Crear proyecto en Google Cloud

1. Ve a: https://console.cloud.google.com
2. Haz clic en "Seleccionar proyecto" → "Nuevo proyecto"
3. Nombre: "Pipeline Ventas" → Crear

## PASO 2 — Activar la API de Drive

1. En el menú izquierdo: "APIs y servicios" → "Biblioteca"
2. Busca "Google Drive API"
3. Haz clic en ella → "Habilitar"

## PASO 3 — Crear credenciales OAuth2

1. "APIs y servicios" → "Credenciales"
2. "Crear credenciales" → "ID de cliente OAuth"
3. Si pide configurar pantalla de consentimiento:
   - Tipo de usuario: "Externo" → Crear
   - Nombre de la app: "Pipeline Ventas"
   - Correo de asistencia: tu correo → Guardar
   - En "Usuarios de prueba": agrega tu correo de Google → Guardar
4. Vuelve a "Crear credenciales" → "ID de cliente OAuth"
5. Tipo de aplicación: "Aplicación de escritorio"
6. Nombre: "Pipeline Ventas Desktop"
7. Crear → "Descargar JSON"

## PASO 4 — Instalar el archivo

1. Renombra el archivo descargado a: credentials.json
2. Cópialo a: C:\Scripts\BackupManager\credentials.json

## PASO 5 — Instalar dependencias

Ejecuta en la terminal:
    pip install google-auth google-auth-oauthlib google-api-python-client

## PASO 6 — Autorizar (solo la primera vez)

Ejecuta:
    python 02_subir_a_drive.py

Se abrirá el navegador para que aceptes el acceso.
Después de aceptar, se crea token.json automáticamente
y ya no necesitas hacerlo nunca más.

## ESTRUCTURA FINAL DE ARCHIVOS

C:\Scripts\BackupManager\
├── descargar_backup_manager.py   ← descarga el .bak
├── 01_restaurar_y_extraer.py     ← restaura BD + exporta Excel
├── 02_subir_a_drive.py           ← sube a Drive
├── 00_pipeline_completo.py       ← orquestador (corre todo)
├── ejecutar_pipeline.bat         ← lo que ejecuta Task Scheduler
├── credentials.json              ← tu credencial de Google (no compartir)
└── token.json                    ← se genera automáticamente

## CONECTAR GOOGLE SHEETS AL EXCEL EN DRIVE

Para que tu Google Sheets se actualice solo:

1. Abre Google Sheets
2. Menú: Datos → Conectores de datos → Conectar con Drive
   (o usa la fórmula IMPORTDATA si el archivo es CSV)

ALTERNATIVA más robusta con Excel:
1. En el Excel de Drive, haz clic derecho → "Abrir con Google Sheets"
2. Google Sheets → Datos → Actualizar datos

O desde Google Sheets directamente:
1. Datos → Importar → Google Drive → selecciona VentasFull_Actualizado.xlsx
2. Cada vez que el script actualice el archivo, 
   refresca en Sheets con Datos → Actualizar todas

## NOTAS IMPORTANTES

- El script REEMPLAZA el mismo archivo en Drive cada día
  (mismo ID de archivo → los links y dashboards no se rompen)
- Los logs se guardan en: C:\Scripts\BackupManager\pipeline_ventas.log
- Si hay error, revisa el log para ver en qué paso falló
