@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto use_py

python backend\app.py
goto finished

:use_py
where py >nul 2>nul
if errorlevel 1 goto no_python
py -3 backend\app.py
goto finished

:no_python
echo.
echo ERRO: Python nao foi encontrado neste computador.
echo Instale o Python em https://www.python.org/downloads/ e tente novamente.
pause
exit /b 1

:finished
if errorlevel 1 (
  echo.
  echo O servidor nao conseguiu iniciar. A mensagem acima indica o motivo.
  pause
)
