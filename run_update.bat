@echo off
REM ============================================================
REM  run_update.bat — Lanzador para Task Scheduler de Windows
REM  Actualiza datos de heladas y regenera el dashboard HTML.
REM
REM  Configurar en Task Scheduler:
REM    Programa/script : C:\Windows\System32\cmd.exe
REM    Argumentos      : /c "C:\Users\s1134058\heladas-argentina\run_update.bat"
REM    Iniciar en      : C:\Users\s1134058\heladas-argentina
REM ============================================================

cd /d "%~dp0"

echo [%DATE% %TIME%] Iniciando actualizacion del dashboard...

REM Correr el script de orquestacion con uv
uv run python update_dashboard.py

REM Capturar el codigo de salida
set EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE% EQU 0 (
    echo [%DATE% %TIME%] Actualizacion completada exitosamente.
) else (
    echo [%DATE% %TIME%] ERROR: La actualizacion fallo con codigo %EXIT_CODE%.
    echo Revisa los logs en: %~dp0logs\
)

exit /b %EXIT_CODE%
