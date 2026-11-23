"""Conversión de DWG a DXF con motor elegible.

* ODA File Converter: gratuito, licencia propietaria, mejor compatibilidad
  con versiones recientes de AutoCAD. Descarga: opendesign.com (ODA File Converter).
* LibreDWG (dwg2dxf): libre (GPL). Puede fallar con DWG muy recientes.
* auto: intenta ODA y, si no está o falla, LibreDWG.

Después de convertir, el DXF se lee con ezdxf.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from core import ajustes

MOTORES = ("auto", "oda", "libredwg")


def _ruta_oda() -> str | None:
    r = ajustes.obtener("conversion_dwg.ruta_oda", "") or ""
    if r and Path(r).exists():
        return r
    return shutil.which("ODAFileConverter") or shutil.which("ODAFileConverter.exe")


def _ruta_libredwg() -> str | None:
    r = ajustes.obtener("conversion_dwg.ruta_libredwg", "") or ""
    if r and Path(r).exists():
        return r
    return shutil.which("dwg2dxf") or shutil.which("dwg2dxf.exe")


def disponibles() -> dict[str, str | None]:
    return {"oda": _ruta_oda(), "libredwg": _ruta_libredwg()}


def _con_oda(exe: str, dwg: Path, salida: Path) -> Path:
    version = ajustes.obtener("conversion_dwg.version_dxf", "ACAD2018")
    with tempfile.TemporaryDirectory() as ent:
        shutil.copy2(dwg, Path(ent) / dwg.name)
        # Sintaxis: ODAFileConverter <dir_entrada> <dir_salida> <versión> <tipo> <recursivo> <auditar> [filtro]
        subprocess.run([exe, ent, str(salida.parent), version, "DXF", "0", "1", dwg.name],
                       check=True, capture_output=True, timeout=300)
    dxf = salida.parent / (dwg.stem + ".dxf")
    if not dxf.exists():
        raise RuntimeError("ODA File Converter no generó el DXF.")
    return dxf


def _con_libredwg(exe: str, dwg: Path, salida: Path) -> Path:
    subprocess.run([exe, "-y", "-o", str(salida), str(dwg)], check=True, capture_output=True, timeout=300)
    if not salida.exists():
        raise RuntimeError("dwg2dxf no generó el DXF.")
    return salida


def dwg_a_dxf(dwg: Path, carpeta_salida: Path, motor: str | None = None) -> dict:
    """Convierte y devuelve {dxf, motor, avisos}. Lanza RuntimeError si no hay motor."""
    dwg = Path(dwg)
    carpeta_salida.mkdir(parents=True, exist_ok=True)
    salida = carpeta_salida / (dwg.stem + ".dxf")
    motor = motor or ajustes.obtener("conversion_dwg.motor", "auto")
    rutas = disponibles()
    orden = ["oda", "libredwg"] if motor == "auto" else [motor]
    avisos = []
    for m in orden:
        exe = rutas.get(m)
        if not exe:
            avisos.append(f"{m}: no instalado o ruta no configurada.")
            continue
        try:
            dxf = _con_oda(exe, dwg, salida) if m == "oda" else _con_libredwg(exe, dwg, salida)
            return {"dxf": dxf, "motor": m, "avisos": avisos}
        except Exception as e:
            avisos.append(f"{m}: falló ({e}).")
    raise RuntimeError("No se pudo convertir el DWG. " + " ".join(avisos) +
                       " Instale ODA File Converter o LibreDWG y configure la ruta, "
                       "o pida al solicitante el archivo en DXF.")
