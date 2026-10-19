"""Genera SUPABASE_KEY: un JWT con "role": "licitaciones_m5" (permisos mínimos sobre m5.licitaciones_mp).

Correrlo UNA vez, en tu propia ventana de PowerShell (no con "!" dentro de Claude Code), después de
aplicar supabase/licitaciones_mp_evaluacion.sql:

    .venv\\Scripts\\python generar_clave_supabase.py            # escribe SUPABASE_URL y SUPABASE_KEY en .env
    .venv\\Scripts\\python generar_clave_supabase.py --github   # además los guarda como secrets de GrupoSHG/Scripts

Pide el "JWT Secret" del proyecto (Supabase → Project Settings → JWT Keys → Legacy JWT Secret) con
entrada oculta. El secret y el JWT nunca se muestran en pantalla ni se escriben fuera de .env / GitHub.
"""
import argparse
import base64
import getpass
import hashlib
import hmac
import json
import subprocess
import sys
import time
from pathlib import Path

PROYECTO = "ffxopvzxyeacpbtxuagu"
URL = f"https://{PROYECTO}.supabase.co"
ROL = "licitaciones_m5"
REPO = "GrupoSHG/Scripts"
ENV = Path(__file__).resolve().parent / ".env"


def _b64(datos):
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode()


def firmar(secret, anios):
    ahora = int(time.time())
    cabecera = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    cuerpo = _b64(json.dumps({"iss": "supabase", "ref": PROYECTO, "role": ROL, "iat": ahora,
                              "exp": ahora + anios * 365 * 86400}, separators=(",", ":")).encode())
    firma = hmac.new(secret.encode(), f"{cabecera}.{cuerpo}".encode(), hashlib.sha256).digest()
    return f"{cabecera}.{cuerpo}.{_b64(firma)}"


def escribir_env(valores):
    lineas = ENV.read_text(encoding="utf-8-sig").splitlines() if ENV.is_file() else []
    pendientes = dict(valores)
    for i, linea in enumerate(lineas):
        clave = linea.partition("=")[0].strip()
        if clave in pendientes:
            lineas[i] = f"{clave}={pendientes.pop(clave)}"
    lineas += [f"{k}={v}" for k, v in pendientes.items()]
    ENV.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--github", action="store_true", help=f"guardar también los secrets en {REPO} con gh")
    ap.add_argument("--anios", type=int, default=3, help="vigencia del JWT (años)")
    args = ap.parse_args()

    secret = getpass.getpass("JWT Secret del proyecto (no se muestra): ").strip()
    if len(secret) < 32:
        sys.exit("Ese valor es muy corto para ser el JWT Secret. No se escribió nada.")
    clave = firmar(secret, args.anios)
    escribir_env({"SUPABASE_URL": URL, "SUPABASE_KEY": clave})
    print(f"Listo: SUPABASE_URL y SUPABASE_KEY (rol {ROL}, {args.anios} años) escritos en {ENV.name}.")
    if args.github:
        for nombre, valor in (("SUPABASE_URL", URL), ("SUPABASE_KEY", clave)):
            r = subprocess.run(["gh", "secret", "set", nombre, "-R", REPO], input=valor, text=True,
                               capture_output=True)
            print(f"Secret {nombre} en {REPO}: {'ok' if r.returncode == 0 else 'ERROR ' + r.stderr.strip()[:200]}")


if __name__ == "__main__":
    main()
