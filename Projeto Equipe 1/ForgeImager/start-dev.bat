@echo off
setlocal
set "PATH=%PATH%;%USERPROFILE%\.cargo\bin;C:\Program Files\Git\cmd;C:\Program Files\nodejs"
cd /d "%~dp0"
echo ========================================================
echo   Iniciando Forge Imager em Modo Desenvolvimento
echo   Hot-reloading ativo para React e Rust!
echo ========================================================
npm run tauri:dev
pause
