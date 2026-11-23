"""Rutas del proyecto. Todo se resuelve relativo a la carpeta del programa,
así funciona igual en cualquier computador."""
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CONFIG = BASE / "config"
PARAMETROS = CONFIG / "parametros"
PLANTILLAS = CONFIG / "plantillas"
AJUSTES = CONFIG / "ajustes.yaml"
DATOS = BASE / "datos"
BD_DIR = DATOS / "bd"
NORMAS_DIR = DATOS / "normas"
CAPAS_DIR = DATOS / "capas"
EXPEDIENTES_DIR = DATOS / "expedientes"
TEMP_DIR = DATOS / "temp"

for _d in (BD_DIR, NORMAS_DIR, CAPAS_DIR, EXPEDIENTES_DIR, TEMP_DIR):
    _d.mkdir(parents=True, exist_ok=True)
