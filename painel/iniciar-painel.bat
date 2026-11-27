@echo off
chcp 65001 >nul
title Painel de Controle
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python nao encontrado. Instale em python.org marcando "Add python.exe to PATH".
  pause
  exit /b 1
)

rem Atualiza o painel (se o Git estiver instalado)
where git >nul 2>nul && git pull --ff-only

rem Instala o que faltar (so na primeira vez)
python -c "import fastapi, uvicorn, psutil, qrcode" 2>nul || python -m pip install -r requirements.txt

:inicio
python servidor.py
echo.
echo O painel parou. Reiniciando em 5 segundos... (feche a janela para encerrar)
timeout /t 5 >nul
goto inicio
