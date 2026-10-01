@echo off
rem Envia um e-mail de teste usando os dados do arquivo .env
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" buscador.py --testar-notificacao
pause
