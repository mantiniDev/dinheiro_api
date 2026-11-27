@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$atalho = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup') + '\Painel de Controle.lnk');" ^
  "$atalho.TargetPath = '%~dp0iniciar-painel.bat';" ^
  "$atalho.WorkingDirectory = '%~dp0';" ^
  "$atalho.WindowStyle = 7;" ^
  "$atalho.Description = 'Painel de Controle (celular)';" ^
  "$atalho.Save()"
if errorlevel 1 (
  echo Nao consegui criar o atalho.
) else (
  echo Pronto! O painel vai iniciar sozinho, minimizado, quando o Windows ligar.
  echo Para desfazer, rode remover-inicio-automatico.bat
)
pause
