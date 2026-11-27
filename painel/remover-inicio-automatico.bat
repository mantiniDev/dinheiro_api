@echo off
chcp 65001 >nul
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Painel de Controle.lnk" 2>nul
echo O painel nao vai mais iniciar junto com o Windows.
pause
