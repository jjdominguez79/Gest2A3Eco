@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0publicar_version.ps1"
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo.
  echo La publicacion ha fallado. Revisa el mensaje anterior.
  pause
)
exit /b %EXITCODE%
