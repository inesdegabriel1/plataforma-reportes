@echo off
rem Arranca el backend en una ventana minimizada (si no esta ya arrancado).
rem Lo lanza el boton "Arrancar backend" de la web; tambien se puede abrir con doble clic.
rem No usa parametros a proposito: nada de la URL que lo invoca llega al backend.
setlocal
set "PORT=8000"

netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul && exit /b 0

cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo No encuentro backend\.venv\Scripts\python.exe. Sigue el paso 1 del README.
  pause
  exit /b 1
)

start "Swiftair EHM - backend (cierra esta ventana para apagarlo)" /min ".venv\Scripts\python.exe" -m uvicorn app.main:app --port %PORT%
