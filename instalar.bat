@echo off
chcp 65001 >nul
echo ============================================================
echo  Instalacion - Tramites urbanisticos El Carmen de Viboral
echo ============================================================
where python >nul 2>nul
if errorlevel 1 (
  echo No se encontro Python. Instale Python 3.11 o superior desde python.org
  echo y marque la casilla "Add Python to PATH". Luego vuelva a ejecutar este archivo.
  pause
  exit /b 1
)
cd /d "%~dp0"
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo Instalacion terminada. Para abrir el programa haga doble clic en iniciar.bat
echo (Para OCR local instale tambien Tesseract con idioma espanol; ver docs\INSTALACION.md)
pause
