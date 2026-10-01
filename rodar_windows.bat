@echo off
rem Executado todo dia pelo Agendador de Tarefas. Pode rodar manualmente tambem.
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
echo ===== %date% %time% ===== >> busca.log
".venv\Scripts\python.exe" buscador.py >> busca.log 2>&1
