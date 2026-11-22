@echo off
rem Activa el boton "Arrancar backend" de la web (solo hay que hacerlo una vez).
rem Registra el enlace swiftair-ehm:// para TU usuario de Windows (HKCU, sin permisos de
rem administrador) apuntando a arrancar.cmd. Para quitarlo: instalar-boton.cmd /desinstalar
setlocal
set "KEY=HKCU\Software\Classes\swiftair-ehm"

if /i "%~1"=="/desinstalar" (
  reg delete "%KEY%" /f >nul 2>&1
  echo Boton desactivado.
  pause
  exit /b 0
)

set "SCRIPT=%~dp0arrancar.cmd"
reg add "%KEY%" /ve /d "URL:Swiftair Engine Health" /f >nul
reg add "%KEY%" /v "URL Protocol" /d "" /f >nul
reg add "%KEY%\shell\open\command" /ve /d "\"%SCRIPT%\"" /f >nul

echo Listo. El boton "Arrancar backend" de la web ya funciona.
echo La primera vez Chrome preguntara si quieres abrir el enlace: marca "Permitir siempre".
echo Si mueves la carpeta del proyecto, vuelve a ejecutar este archivo.
pause
