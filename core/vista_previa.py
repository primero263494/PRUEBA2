"""Vista previa de documentos dentro del programa.

Devuelve un dict con el tipo de vista y su contenido; la página decide cómo
mostrarlo. Nunca modifica el archivo original.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from core.rutas import TEMP_DIR

IMAGENES = {"png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp"}


def pdf_paginas(ruta: Path, desde: int = 1, cuantas: int = 3, dpi: int = 110) -> dict:
    ruta = Path(ruta)
    salida = TEMP_DIR / f"vp_{ruta.stem}_{abs(hash(str(ruta))) % 10**8}"
    salida.mkdir(parents=True, exist_ok=True)
    try:
        import fitz
        doc = fitz.open(ruta)
        total = doc.page_count
        imgs = []
        for i in range(desde - 1, min(total, desde - 1 + cuantas)):
            p = salida / f"p{i + 1}.png"
            if not p.exists():
                doc[i].get_pixmap(dpi=dpi).save(p)
            imgs.append(p)
        return {"tipo": "imagenes", "imagenes": imgs, "paginas": total}
    except ImportError:
        pass
    if shutil.which("pdftoppm"):
        hasta = desde + cuantas - 1
        subprocess.run(["pdftoppm", "-f", str(desde), "-l", str(hasta), "-r", str(dpi), "-png", str(ruta),
                        str(salida / "p")], check=True, capture_output=True)
        total = None
        if shutil.which("pdfinfo"):
            info = subprocess.run(["pdfinfo", str(ruta)], capture_output=True, text=True).stdout
            for linea in info.splitlines():
                if linea.startswith("Pages:"):
                    total = int(linea.split()[1])
        return {"tipo": "imagenes", "imagenes": sorted(salida.glob("p*.png")), "paginas": total}
    return {"tipo": "sin_vista", "mensaje": "Instale PyMuPDF para ver PDF dentro del programa."}


def dxf_resumen(ruta: Path) -> dict:
    try:
        import ezdxf
    except ImportError:
        return {"tipo": "sin_vista", "mensaje": "Instale ezdxf para leer DXF."}
    doc = ezdxf.readfile(str(ruta))
    msp = doc.modelspace()
    conteo: dict[str, int] = {}
    for e in msp:
        conteo[e.dxftype()] = conteo.get(e.dxftype(), 0) + 1
    capas = sorted(l.dxf.name for l in doc.layers)
    textos = [e.dxf.text for e in msp.query("TEXT")][:50] + [e.text for e in msp.query("MTEXT")][:50]
    img = None
    try:
        import matplotlib
        matplotlib.use("Agg")
        from ezdxf.addons.drawing import matplotlib as dm
        img = TEMP_DIR / f"dxf_{Path(ruta).stem}.png"
        dm.qsave(msp, str(img), bg="#FFFFFF")
    except Exception:
        img = None
    unidades = {0: "sin unidad", 1: "pulgadas", 4: "mm", 5: "cm", 6: "m"}.get(doc.header.get("$INSUNITS", 0), "otra")
    return {"tipo": "dxf", "version": doc.dxfversion, "unidades": unidades, "capas": capas,
            "entidades": conteo, "textos": textos, "imagen": img}


def generar(ruta: Path, extension: str, pagina: int = 1) -> dict:
    ruta, ext = Path(ruta), extension.lower()
    if not ruta.exists():
        return {"tipo": "sin_vista", "mensaje": "El archivo no se encuentra en disco."}
    if ext == "pdf":
        return pdf_paginas(ruta, desde=pagina)
    if ext in IMAGENES:
        if ext in ("tif", "tiff", "bmp"):
            from PIL import Image
            png = TEMP_DIR / f"vp_{ruta.stem}.png"
            Image.open(ruta).save(png)
            return {"tipo": "imagenes", "imagenes": [png], "paginas": 1}
        return {"tipo": "imagenes", "imagenes": [ruta], "paginas": 1}
    if ext == "docx":
        import docx
        d = docx.Document(ruta)
        texto = "\n".join(p.text for p in d.paragraphs)
        tablas = [[[c.text for c in f.cells] for f in t.rows] for t in d.tables]
        return {"tipo": "texto", "texto": texto[:20000], "tablas": tablas[:5]}
    if ext in ("xlsx", "xls", "csv"):
        import pandas as pd
        if ext == "csv":
            return {"tipo": "tablas", "tablas": {"datos": pd.read_csv(ruta, nrows=500, sep=None, engine="python")}}
        hojas = pd.read_excel(ruta, sheet_name=None, nrows=500)
        return {"tipo": "tablas", "tablas": hojas}
    if ext in ("txt", "e2k", "s2k", "f2k", "geojson", "prj"):
        return {"tipo": "texto", "texto": ruta.read_text(encoding="utf-8", errors="replace")[:20000], "tablas": []}
    if ext == "dxf":
        return dxf_resumen(ruta)
    if ext == "dwg":
        try:
            from core import conversores
            r = conversores.dwg_a_dxf(ruta, TEMP_DIR / "dwg")
            v = dxf_resumen(r["dxf"])
            v["nota"] = f"Convertido con {r['motor']}."
            return v
        except Exception as e:
            return {"tipo": "sin_vista", "mensaje": f"No se pudo convertir el DWG: {e}"}
    return {"tipo": "sin_vista", "mensaje": f"Sin vista previa para .{ext}; use Descargar."}
