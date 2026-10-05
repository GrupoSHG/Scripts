@echo off
rem Lo ejecuta el Programador de tareas (tarea "Polchile - Descargas Manager").
cd /d "%~dp0"
if not exist logs mkdir logs
set PYTHONIOENCODING=utf-8
for /f "tokens=1-3 delims=/-. " %%a in ("%date%") do set HOY=%%c-%%b-%%a
".venv\Scripts\python.exe" robot.py >> "logs\robot_%HOY%.log" 2>&1
