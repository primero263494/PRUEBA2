"""Respaldo y restauración de todos los datos en un solo archivo .zip.

Incluye la base de datos (expedientes, trámites, usuarios, auditoría,
parámetros modificados, cálculos, análisis, informes), los archivos subidos
(expedientes, normas, capas) y la plantilla de informes con su logo.

Sirve para:
- guardar copias periódicas en el computador de la oficina;
- pasar los datos de un equipo a otro;
- recuperar todo en Streamlit Cloud, cuyo disco se borra cada vez que el
  servidor se reinicia.
"""
from __future__ import annotations

import io
import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

from core import ajustes
from core.rutas import BASE, CAPAS_DIR, EXPEDIENTES_DIR, NORMAS_DIR

PLANTILLAS = BASE / "config" / "plantillas"
CARPETAS = {"datos/expedientes": EXPEDIENTES_DIR, "datos/normas": NORMAS_DIR, "datos/capas": CAPAS_DIR,
            "config/plantillas": PLANTILLAS}
NOMBRE_BD = "datos/bd/tramites.db"
MARCA = "respaldo_tramites.txt"


def en_la_nube() -> bool:
    """True si corre en Streamlit Community Cloud (disco no permanente)."""
    import os
    return str(BASE).startswith("/mount/src") or bool(os.environ.get("STREAMLIT_SHARING_MODE"))


def ultimo() -> str:
    from core import db
    f = db.consultar("SELECT valor FROM sistema WHERE clave='ultimo_respaldo'")
    return f[0]["valor"] if f else ""


def _marcar_respaldo():
    from core import db
    db.ejecutar("INSERT INTO sistema (clave, valor) VALUES ('ultimo_respaldo', datetime('now','localtime')) "
                "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor")


def crear() -> tuple[bytes, str]:
    """Devuelve (contenido del zip, nombre sugerido)."""
    _marcar_respaldo()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(MARCA, f"Respaldo del programa de trámites urbanísticos\nFecha: {datetime.now().isoformat(timespec='seconds')}\n")
        # copia consistente de la base aunque esté en uso
        tmp = ajustes.ruta_bd().with_suffix(".respaldo.db")
        origen = sqlite3.connect(ajustes.ruta_bd())
        destino = sqlite3.connect(tmp)
        with destino:
            origen.backup(destino)
        origen.close()
        destino.close()
        z.write(tmp, NOMBRE_BD)
        tmp.unlink(missing_ok=True)
        for nombre, carpeta in CARPETAS.items():
            if carpeta.exists():
                for f in carpeta.rglob("*"):
                    if f.is_file() and f.name != ".gitkeep":
                        z.write(f, f"{nombre}/{f.relative_to(carpeta).as_posix()}")
    return buf.getvalue(), f"respaldo_tramites_{datetime.now():%Y-%m-%d_%H%M}.zip"


def validar(contenido: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        nombres = z.namelist()
        if MARCA not in nombres or NOMBRE_BD not in nombres:
            raise ValueError("El archivo no es un respaldo de este programa.")
        for n in nombres:
            if n.startswith("/") or ".." in Path(n).parts:
                raise ValueError(f"Ruta no permitida en el respaldo: {n}")
        fecha = z.read(MARCA).decode("utf-8").split("Fecha:")[-1].strip()
        return {"fecha": fecha, "archivos": len(nombres) - 2}


def restaurar(contenido: bytes) -> dict:
    """Reemplaza la base y los archivos por los del respaldo."""
    info = validar(contenido)
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        for carpeta in CARPETAS.values():
            if carpeta.exists() and carpeta != PLANTILLAS:
                shutil.rmtree(carpeta)
            carpeta.mkdir(parents=True, exist_ok=True)
        for n in z.namelist():
            if n == MARCA or n.endswith("/"):
                continue
            if n == NOMBRE_BD:
                destino = ajustes.ruta_bd()
            else:
                raiz, _, resto = next(((k, "/", n[len(k) + 1:]) for k in CARPETAS if n.startswith(k + "/")), (None, "", ""))
                if raiz is None:
                    continue
                destino = CARPETAS[raiz] / resto
            destino.parent.mkdir(parents=True, exist_ok=True)
            with z.open(n) as src, open(destino, "wb") as dst:
                shutil.copyfileobj(src, dst)
    return info
