@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\activate.bat (
  echo Primero ejecute instalar.bat
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
echo Abriendo el programa en el navegador... (no cierre esta ventana mientras lo use)
streamlit run app.py --server.headless false --browser.gatherUsageStats false
