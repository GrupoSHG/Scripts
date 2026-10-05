"""Sube el respaldo de Supabase (pg_dump) a Google Drive y borra los antiguos.

Uso: python respaldo_supabase_drive.py <archivo.dump>
Requiere GOOGLE_CREDENTIALS_JSON (la misma cuenta de servicio que usa el
pipeline para subir el Excel). Deja el archivo en la subcarpeta
"Respaldos Supabase" de la carpeta de Drive del pipeline y conserva solo
los últimos RETENCION_DIAS días.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Misma carpeta que DRIVE_FOLDER_ID en Polchile_Systems/backup-manager/subir_a_drive.py
CARPETA_PIPELINE = "1AQgW1Mrr4MbBNi7yXA8kPNpjZBoo9Ntq"
SUBCARPETA = "Respaldos Supabase"
RETENCION_DIAS = 30
MIME_CARPETA = "application/vnd.google-apps.folder"


def conectar():
    creds = service_account.Credentials.from_service_account_info(
        json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"]),
        scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=creds)


def carpeta_respaldos(drive):
    q = (f"name='{SUBCARPETA}' and '{CARPETA_PIPELINE}' in parents "
         f"and mimeType='{MIME_CARPETA}' and trashed=false")
    r = drive.files().list(q=q, fields="files(id)", supportsAllDrives=True,
                           includeItemsFromAllDrives=True).execute()
    if r["files"]:
        return r["files"][0]["id"]
    meta = {"name": SUBCARPETA, "mimeType": MIME_CARPETA, "parents": [CARPETA_PIPELINE]}
    return drive.files().create(body=meta, fields="id", supportsAllDrives=True).execute()["id"]


def subir(drive, carpeta, ruta):
    media = MediaFileUpload(ruta, mimetype="application/octet-stream", resumable=True)
    meta = {"name": os.path.basename(ruta), "parents": [carpeta]}
    f = drive.files().create(body=meta, media_body=media, fields="id, size, webViewLink",
                             supportsAllDrives=True).execute()
    print(f"Subido a Drive: {os.path.basename(ruta)} ({int(f.get('size', 0)) / 1e6:.1f} MB) {f.get('webViewLink', '')}")


def borrar_antiguos(drive, carpeta):
    limite = datetime.now(timezone.utc) - timedelta(days=RETENCION_DIAS)
    q = (f"'{carpeta}' in parents and trashed=false and name contains 'respaldo_supabase_' "
         f"and createdTime < '{limite.strftime('%Y-%m-%dT%H:%M:%S')}'")
    r = drive.files().list(q=q, fields="files(id, name)", supportsAllDrives=True,
                           includeItemsFromAllDrives=True).execute()
    for f in r["files"]:
        drive.files().delete(fileId=f["id"], supportsAllDrives=True).execute()
        print(f"Borrado por antigüedad: {f['name']}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not os.path.exists(sys.argv[1]):
        raise SystemExit(__doc__)
    drive = conectar()
    carpeta = carpeta_respaldos(drive)
    subir(drive, carpeta, sys.argv[1])
    borrar_antiguos(drive, carpeta)
