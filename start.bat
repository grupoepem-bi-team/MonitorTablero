@echo off
REM ============================================================
REM  start.bat - Levanta el Monitor de Tableros
REM  Verifica puerto, luego levanta uvicorn o docker
REM ============================================================

set PORT=8501

echo.
echo  Monitor de Tableros - Inicio
echo  ============================
echo.

REM Verificar puerto
echo Verificando puerto %PORT%...
python scripts\check_port.py %PORT%
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Puerto %PORT% ocupado. Abortando.
    echo Editar start.bat para cambiar PORT o detener el proceso que lo usa.
    pause
    exit /b 1
)

echo Puerto libre. Levantando servidor...
echo.

REM Verificar si queremos Docker o local
if "%1"=="--docker" (
    echo Modo Docker...
    docker compose up -d --build
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo Error levantando Docker. Verificar que Docker Desktop este corriendo.
        pause
        exit /b 1
    )
    echo.
    echo Monitor levantado en Docker: http://localhost:%PORT%
    echo Logs: docker compose logs -f
) else (
    echo Modo local...
    .venv\Scripts\python.exe -m uvicorn frontend.server:app --host 127.0.0.1 --port %PORT%
)

pause