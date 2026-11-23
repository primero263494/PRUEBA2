"""Lectores de modelos CSI exportados a texto: ETABS (.e2k) y SAP2000/SAFE
(.s2k/.f2k). Extrae unidades, pisos con alturas, materiales con f'c y fy
convertidos a MPa, sistemas de cargas sísmicas y número de elementos.
"""
from __future__ import annotations

import re
from pathlib import Path

# factor para convertir esfuerzo (fuerza/longitud²) a MPa
A_MPA = {
    ("KN", "M"): 0.001, ("KN", "MM"): 1000.0, ("KN", "CM"): 10.0,
    ("N", "MM"): 1.0, ("N", "M"): 1e-6, ("N", "CM"): 0.01,
    ("KGF", "CM"): 0.0980665, ("KGF", "M"): 9.80665e-6, ("KGF", "MM"): 9.80665,
    ("TONF", "M"): 0.00980665, ("TONF", "CM"): 98.0665,
    ("LB", "IN"): 0.00689476, ("KIP", "IN"): 6.89476, ("KIP", "FT"): 0.0478803, ("LB", "FT"): 4.78803e-5,
}
A_METRO = {"M": 1.0, "CM": 0.01, "MM": 0.001, "IN": 0.0254, "FT": 0.3048}


def _comillas(linea: str) -> list[str]:
    return re.findall(r'"([^"]*)"', linea)


def _kv(linea: str) -> dict:
    """Pares PALABRA valor / Clave=valor de una línea."""
    d = {}
    for k, v in re.findall(r'(\w+)\s*=\s*("[^"]*"|\S+)', linea):
        d[k.upper()] = v.strip('"')
    toks = re.findall(r'"[^"]*"|\S+', linea)
    for i in range(len(toks) - 1):
        if toks[i].isupper() and not toks[i].startswith('"'):
            d.setdefault(toks[i], toks[i + 1].strip('"'))
    return d


def leer_e2k(ruta: Path) -> dict:
    texto = Path(ruta).read_text(encoding="utf-8", errors="replace")
    fuerza, longitud = "KN", "M"
    m = re.search(r'UNITS\s+"([^"]+)"\s+"([^"]+)"', texto)
    if m:
        fuerza, longitud = m.group(1).upper(), m.group(2).upper()
    seccion = None
    pisos, materiales, puntos, frames, areas, cargas = [], {}, 0, 0, 0, []
    for linea in texto.splitlines():
        s = linea.strip()
        if s.startswith("$"):
            seccion = s[1:].strip().upper()
            continue
        if not s:
            continue
        if seccion and seccion.startswith("STORIES") and s.upper().startswith("STORY"):
            nombre = _comillas(s)[0] if _comillas(s) else "?"
            kv = _kv(s)
            pisos.append({"nombre": nombre, "altura": float(kv["HEIGHT"]) if "HEIGHT" in kv else None,
                          "elevacion": float(kv["ELEV"]) if "ELEV" in kv else None})
        elif seccion and seccion.startswith("MATERIAL") and s.upper().startswith("MATERIAL"):
            nombre = _comillas(s)[0] if _comillas(s) else "?"
            kv = _kv(s)
            m_ = materiales.setdefault(nombre, {})
            if "TYPE" in kv:
                m_["tipo"] = kv["TYPE"]
            for clave in ("FC", "FY", "FU", "E"):
                if clave in kv:
                    try:
                        m_[clave.lower()] = float(kv[clave])
                    except ValueError:
                        pass
        elif seccion and seccion.startswith("POINT COORDINATES"):
            puntos += 1
        elif seccion and seccion.startswith("LINE CONNECTIVITIES"):
            frames += 1
        elif seccion and seccion.startswith("AREA CONNECTIVITIES"):
            areas += 1
        elif seccion and seccion.startswith("LOAD PATTERNS"):
            q = _comillas(s)
            if q:
                cargas.append({"nombre": q[0], "tipo": _kv(s).get("TYPE", "")})
    return _normalizar("ETABS .e2k", fuerza, longitud, pisos, materiales,
                       {"puntos": puntos, "elementos_lineales": frames, "elementos_area": areas}, cargas)


def leer_s2k(ruta: Path) -> dict:
    texto = Path(ruta).read_text(encoding="utf-8", errors="replace")
    fuerza, longitud = "KN", "M"
    m = re.search(r'CurrUnits\s*=\s*"\s*([A-Za-z]+)\s*,\s*([A-Za-z]+)', texto)
    if m:
        fuerza, longitud = m.group(1).upper(), m.group(2).upper()
    tabla = None
    materiales, pisos, conteo, cargas = {}, [], {"puntos": 0, "elementos_lineales": 0, "elementos_area": 0}, []
    for linea in texto.splitlines():
        s = linea.strip()
        if s.upper().startswith("TABLE:"):
            tabla = s.split(":", 1)[1].strip().strip('"').upper()
            continue
        if not s or tabla is None:
            continue
        kv = _kv(s)
        if "MATERIAL PROPERTIES" in tabla and "MATERIAL" in kv:
            m_ = materiales.setdefault(kv["MATERIAL"], {})
            if "TYPE" in kv:
                m_["tipo"] = kv["TYPE"]
            for clave in ("FC", "FY", "FU", "E1"):
                if clave in kv:
                    try:
                        m_[clave.lower().rstrip("1")] = float(kv[clave])
                    except ValueError:
                        pass
        elif tabla.startswith("JOINT COORDINATES"):
            conteo["puntos"] += 1
        elif tabla.startswith("CONNECTIVITY - FRAME"):
            conteo["elementos_lineales"] += 1
        elif tabla.startswith("CONNECTIVITY - AREA"):
            conteo["elementos_area"] += 1
        elif tabla.startswith("LOAD PATTERN DEFINITIONS") and "LOADPAT" in kv:
            cargas.append({"nombre": kv["LOADPAT"], "tipo": kv.get("DESIGNTYPE", "")})
        elif "STORY" in tabla and "STORY" in kv:
            pisos.append({"nombre": kv["STORY"], "altura": float(kv["HEIGHT"]) if "HEIGHT" in kv else None,
                          "elevacion": float(kv["ELEVATION"]) if "ELEVATION" in kv else None})
    return _normalizar("SAP2000/SAFE .s2k", fuerza, longitud, pisos, materiales, conteo, cargas)


def _normalizar(fmt, fuerza, longitud, pisos, materiales, conteo, cargas) -> dict:
    f_mpa = A_MPA.get((fuerza, longitud))
    f_m = A_METRO.get(longitud, 1.0)
    for p in pisos:
        for k in ("altura", "elevacion"):
            if p.get(k) is not None:
                p[k] = round(p[k] * f_m, 3)
    for m in materiales.values():
        for k in ("fc", "fy", "fu"):
            if k in m and f_mpa:
                m[f"{k}_mpa"] = round(m[k] * f_mpa, 2)
    concreto = [m["fc_mpa"] for m in materiales.values() if m.get("fc_mpa")]
    acero = [m["fy_mpa"] for m in materiales.values() if m.get("fy_mpa")]
    alturas = [p["altura"] for p in pisos if p.get("altura")]
    sismo = [c["nombre"] for c in cargas if "SEISM" in c["tipo"].upper() or "QUAKE" in c["tipo"].upper()]
    return {"formato": fmt, "unidades": f"{fuerza}, {longitud}", "pisos": pisos, "n_pisos": len(alturas),
            "alturas_entrepiso": list(reversed(alturas)), "materiales": materiales,
            "fc_mpa": sorted(set(concreto)), "fy_mpa": sorted(set(acero)), "conteo": conteo,
            "cargas_sismicas": sismo, "aviso": None if f_mpa else f"Unidades {fuerza}-{longitud} sin conversión a MPa."}


def leer(ruta: Path) -> dict:
    ext = Path(ruta).suffix.lower()
    return leer_e2k(ruta) if ext == ".e2k" else leer_s2k(ruta)
