@echo off
:: ejecutar_pipeline.bat
:: Se ejecuta al iniciar sesion en Windows via Task Scheduler

set SCRIPT_DIR=C:\Scripts\BackupManager
cd /d "%SCRIPT_DIR%"

:: Espera 60s para que la red este disponible
timeout /t 60 /nobreak > nul

:: Notificacion de inicio
python notificar.py "Pipeline Polchile" "Iniciando descarga y actualizacion de reportes..."

echo %date% %time% - Iniciando pipeline >> "%SCRIPT_DIR%\pipeline_ventas.log"

:: Ejecuta el pipeline completo
python 00_pipeline_completo.py >> "%SCRIPT_DIR%\pipeline_ventas.log" 2>&1

:: Notificacion segun resultado
if errorlevel 1 (
    echo %date% %time% - ERROR en el pipeline >> "%SCRIPT_DIR%\pipeline_ventas.log"
    python notificar.py "Pipeline Polchile ERROR" "Fallo el pipeline. Revisa pipeline_main.log"
    ) else (
    echo %date% %time% - Pipeline completado OK >> "%SCRIPT_DIR%\pipeline_ventas.log"
    python notificar.py "Pipeline Polchile OK" "Reportes actualizados correctamente en Google Sheets."
)