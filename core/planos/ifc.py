"""Lector IFC (STEP, texto). Usa ifcopenshell si está instalado; si no, un
lector propio que extrae pisos (IfcBuildingStorey) con su elevación, espacios,
áreas de cantidades (IfcQuantityArea), unidades y conteo de elementos.
"""
from __future__ import annotations

import re
from pathlib import Path

ELEMENTOS = ("IFCWALL", "IFCWALLSTANDARDCASE", "IFCCOLUMN", "IFCBEAM", "IFCSLAB", "IFCFOOTING", "IFCPILE",
             "IFCSTAIR", "IFCDOOR", "IFCWINDOW", "IFCSPACE", "IFCREINFORCINGBAR", "IFCMEMBER", "IFCROOF")
PREFIJOS = {".MILLI.": 0.001, ".CENTI.": 0.01, ".DECI.": 0.1, "$": 1.0}


def _args(cuerpo: str) -> list[str]:
    """Separa los argumentos STEP de primer nivel respetando comillas y paréntesis."""
    salida, actual, nivel, en_texto = [], [], 0, False
    i = 0
    while i < len(cuerpo):
        c = cuerpo[i]
        if c == "'" and not en_texto:
            en_texto = True
        elif c == "'" and en_texto:
            if i + 1 < len(cuerpo) and cuerpo[i + 1] == "'":
                actual.append("'")
                i += 2
                continue
            en_texto = False
        elif not en_texto and c == "(":
            nivel += 1
        elif not en_texto and c == ")":
            nivel -= 1
        elif not en_texto and c == "," and nivel == 0:
            salida.append("".join(actual).strip())
            actual = []
            i += 1
            continue
        actual.append(c)
        i += 1
    salida.append("".join(actual).strip())
    return salida


def _txt(a: str) -> str:
    return a[1:-1] if a.startswith("'") and a.endswith("'") else a


def _leer_propio(ruta: Path) -> dict:
    texto = Path(ruta).read_text(encoding="utf-8", errors="replace")
    esquema = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", texto)
    entidades = re.findall(r"^#\d+\s*=\s*([A-Z0-9_]+)\s*\((.*)\);\s*$", texto, re.MULTILINE)
    escala = 1.0
    conteo: dict[str, int] = {}
    pisos, espacios, areas = [], [], []
    for tipo, cuerpo in entidades:
        if tipo in ELEMENTOS:
            conteo[tipo] = conteo.get(tipo, 0) + 1
        if tipo == "IFCSIUNIT":
            a = _args(cuerpo)
            if len(a) >= 4 and a[1] == ".LENGTHUNIT." and a[3] == ".METRE.":
                escala = PREFIJOS.get(a[2], 1.0)
        elif tipo == "IFCBUILDINGSTOREY":
            a = _args(cuerpo)
            elev = a[9] if len(a) > 9 else "$"
            pisos.append({"nombre": _txt(a[2]), "elevacion": None if elev in ("$", "") else float(elev)})
        elif tipo == "IFCSPACE":
            a = _args(cuerpo)
            espacios.append(_txt(a[2]) if len(a) > 2 else "")
        elif tipo == "IFCQUANTITYAREA":
            a = _args(cuerpo)
            if len(a) >= 4:
                try:
                    areas.append({"nombre": _txt(a[0]), "valor": float(a[3])})
                except ValueError:
                    pass
    for p in pisos:
        if p["elevacion"] is not None:
            p["elevacion"] = round(p["elevacion"] * escala, 3)
    return {"esquema": esquema.group(1) if esquema else "?", "pisos": pisos, "espacios": espacios,
            "areas": areas, "elementos": conteo, "lector": "lector propio"}


def _leer_ifcopenshell(ruta: Path) -> dict:
    import ifcopenshell
    import ifcopenshell.util.unit as uu
    f = ifcopenshell.open(str(ruta))
    escala = uu.calculate_unit_scale(f)
    pisos = [{"nombre": s.Name, "elevacion": round((s.Elevation or 0) * escala, 3)} for s in f.by_type("IfcBuildingStorey")]
    areas = [{"nombre": q.Name, "valor": q.AreaValue} for q in f.by_type("IfcQuantityArea")]
    conteo = {t: len(f.by_type(t)) for t in ("IfcWall", "IfcColumn", "IfcBeam", "IfcSlab", "IfcFooting", "IfcSpace",
                                             "IfcDoor", "IfcWindow", "IfcStair")}
    return {"esquema": f.schema, "pisos": pisos, "espacios": [s.Name for s in f.by_type("IfcSpace")],
            "areas": areas, "elementos": {k.upper(): v for k, v in conteo.items() if v}, "lector": "ifcopenshell"}


def leer(ruta: Path) -> dict:
    try:
        d = _leer_ifcopenshell(ruta)
    except Exception:
        d = _leer_propio(ruta)
    pisos = sorted([p for p in d["pisos"] if p["elevacion"] is not None], key=lambda p: p["elevacion"])
    alturas = [round(b["elevacion"] - a["elevacion"], 3) for a, b in zip(pisos, pisos[1:])]
    cubiertas = ("cubierta", "techo", "roof", "azotea", "terraza")
    sobre_terreno = [p for p in pisos if p["elevacion"] >= -0.01
                     and not any(c in (p["nombre"] or "").lower() for c in cubiertas)]
    bruta = sum(a["valor"] for a in d["areas"] if "gross" in a["nombre"].lower() and "floor" in a["nombre"].lower())
    e = d["elementos"]
    estructural = e.get("IFCBEAM", 0) + e.get("IFCCOLUMN", 0) + e.get("IFCFOOTING", 0)
    arquitectonico = e.get("IFCSPACE", 0) + e.get("IFCDOOR", 0) + e.get("IFCWINDOW", 0)
    d.update(pisos=pisos, alturas_entrepiso=alturas, n_pisos=len(sobre_terreno),
             area_bruta_pisos=round(bruta, 2) if bruta else None,
             disciplina="estructural" if estructural > arquitectonico else "arquitectonico")
    return d
