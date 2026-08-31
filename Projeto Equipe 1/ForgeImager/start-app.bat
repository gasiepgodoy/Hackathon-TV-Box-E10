@echo off
setlocal
cd /d "%~dp0\src-tauri\target\debug"
if exist "forge-imager.exe" (
    echo Iniciando Forge Imager...
    start "" "forge-imager.exe"
) else (
    echo Executavel nao encontrado. Execute build.bat primeiro.
    pause
)
