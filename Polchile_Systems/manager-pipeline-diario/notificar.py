"""
notificar.py
============
Muestra una notificación en Windows sin librerías externas.
Uso: python notificar.py "Título" "Mensaje"
"""

import sys
import os
import subprocess

titulo  = sys.argv[1] if len(sys.argv) > 1 else "Pipeline Polchile"
mensaje = sys.argv[2] if len(sys.argv) > 2 else "Proceso completado."

# Método 1: BurntToast via PowerShell (Windows 10/11)
ps = f"""
$ErrorActionPreference = 'SilentlyContinue'
[reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null
[reflection.assembly]::loadwithpartialname('System.Drawing') | Out-Null
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.Visible = $true
$notify.ShowBalloonTip(8000, '{titulo}', '{mensaje}', [System.Windows.Forms.ToolTipIcon]::Info)
Start-Sleep -Seconds 9
$notify.Dispose()
"""

resultado = subprocess.run(
    ["powershell", "-WindowStyle", "Hidden", "-Command", ps],
    capture_output=True, text=True
)

# Si no funcionó, fallback con MessageBox (bloqueante pero seguro)
if resultado.returncode != 0:
    ps2 = f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('{mensaje}', '{titulo}')"
    subprocess.run(["powershell", "-Command", ps2])