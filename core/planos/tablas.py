"""Lectura de tablas: Excel/CSV exportados de ETABS/SAP (derivas) y de
laboratorios de suelos (sondeos), y archivos AGS4 (estándar geotécnico abierto).
"""
from __future__ import annotations

import csv
import io
import unicodedata
from pathlib import Path

from core.planos.util import num


def _n(t) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if unicodedata.category(c) != "Mn")


def _hojas(ruta: Path) -> dict:
    import pandas as pd
    ext = ruta.suffix.lower()
    if ext == ".csv":
        crudo = pd.read_csv(ruta, header=None, sep=None, engine="python", dtype=str)
        hojas = {"datos": crudo}
    else:
        hojas = pd.read_excel(ruta, sheet_name=None, header=None, dtype=str)
    salida = {}
    for nombre, df in hojas.items():
        df = df.dropna(how="all")
        if df.empty:
            continue
        # fila de encabezado: la primera con al menos 2 celdas de texto no numérico
        fila_enc = 0
        for i, (_, fila) in enumerate(df.iterrows()):
            textos = [c for c in fila if isinstance(c, str) and c.strip() and num(c) is None]
            if len(textos) >= 2:
                fila_enc = i
                break
        enc = [str(c).strip() if c is not None else f"col{j}" for j, c in enumerate(df.iloc[fila_enc])]
        cuerpo = df.iloc[fila_enc + 1:].copy()
        cuerpo.columns = enc
        salida[nombre] = cuerpo
    return salida


def leer(ruta: Path) -> dict:
    ruta = Path(ruta)
    resultado = {"derivas": [], "deriva_max": None, "sondeos": [], "n_sondeos": None, "profundidad_max": None,
                 "hojas": []}
    for nombre, df in _hojas(ruta).items():
        resultado["hojas"].append(nombre)
        cols = {c: _n(c) for c in df.columns}
        c_deriva = [c for c, n in cols.items() if "drift" in n or "deriva" in n]
        c_piso = next((c for c, n in cols.items() if n.startswith("story") or n.startswith("piso") or "nivel" in n), None)
        for c in c_deriva:
            for _, fila in df.iterrows():
                v = num(fila[c])
                if v is not None:
                    resultado["derivas"].append({"piso": fila[c_piso] if c_piso else "", "valor": v, "columna": c, "hoja": nombre})
        c_id = next((c for c, n in cols.items() if any(k in n for k in ("sondeo", "perfor", "loca_id", "apique", "boring"))), None)
        c_prof = next((c for c, n in cols.items() if "prof" in n or "depth" in n or "fdep" in n), None)
        if c_id:
            ids = {str(x).strip() for x in df[c_id] if str(x).strip() and str(x).strip().lower() != "nan"}
            resultado["sondeos"] += sorted(ids)
        if c_prof:
            prof = [num(x) for x in df[c_prof]]
            prof = [p for p in prof if p is not None]
            if prof:
                resultado["profundidad_max"] = max(prof + [resultado["profundidad_max"] or 0])
    if resultado["derivas"]:
        vals = [d["valor"] for d in resultado["derivas"]]
        mx = max(vals)
        resultado["deriva_max"] = mx / 100 if mx > 0.2 else mx      # valores > 0,2 se asumen en %
    if resultado["sondeos"]:
        resultado["sondeos"] = sorted(set(resultado["sondeos"]))
        resultado["n_sondeos"] = len(resultado["sondeos"])
    return resultado


def leer_ags(ruta: Path) -> dict:
    """AGS4: grupos LOCA (sondeos, LOCA_FDEP profundidad final) y GEOL (estratos)."""
    texto = Path(ruta).read_text(encoding="utf-8", errors="replace")
    grupo, encabezado = None, []
    loca, geol = [], []
    for fila in csv.reader(io.StringIO(texto)):
        if not fila:
            continue
        tipo = fila[0].upper()
        if tipo == "GROUP":
            grupo, encabezado = fila[1].upper(), []
        elif tipo == "HEADING":
            encabezado = [h.upper() for h in fila[1:]]
        elif tipo == "DATA" and encabezado:
            reg = dict(zip(encabezado, fila[1:]))
            if grupo == "LOCA":
                loca.append(reg)
            elif grupo == "GEOL":
                geol.append(reg)
    prof = [num(r.get("LOCA_FDEP")) for r in loca if num(r.get("LOCA_FDEP")) is not None]
    return {"sondeos": [r.get("LOCA_ID") for r in loca], "n_sondeos": len(loca) or None,
            "profundidad_max": max(prof) if prof else None,
            "estratos": [{"sondeo": g.get("LOCA_ID"), "desde": num(g.get("GEOL_TOP")), "hasta": num(g.get("GEOL_BASE")),
                          "descripcion": g.get("GEOL_DESC")} for g in geol][:200],
            "derivas": [], "deriva_max": None, "hojas": ["AGS4"]}
