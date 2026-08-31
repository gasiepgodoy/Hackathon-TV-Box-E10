@echo off
setlocal
set "PATH=%PATH%;%USERPROFILE%\.cargo\bin;C:\Program Files\Git\cmd;C:\Program Files\nodejs"
cd /d "%~dp0"
echo ========================================================
echo   Compilando Forge Imager (Debug / Rapido para Testes)
echo ========================================================
npm run tauri:build:dev
pause
