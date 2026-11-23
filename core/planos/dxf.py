"""Lector DXF (ASCII). Usa ezdxf si está instalado; si no, un lector propio
de códigos de grupo suficiente para capas, textos y polilíneas cerradas.

Extrae: unidades, capas, conteo de entidades, textos y áreas de polilíneas
cerradas por capa. Con eso deduce área del lote, área ocupada y área por
piso cuando las capas tienen nombres reconocibles (LOTE, PREDIO, OCUPACION,
PISO 1, PLACA…), y lee el cuadro de áreas escrito en el plano.
"""
from __future__ import annotations

import re
from pathlib import Path

from core.planos.util import area_poligono

ESCALA_AREA = {0: 1.0, 1: 0.00064516, 2: 0.09290304, 4: 1e-6, 5: 1e-4, 6: 1.0}   # a m²
NOMBRE_UNIDAD = {0: "sin unidad (se asume m)", 1: "pulgadas", 2: "pies", 4: "mm", 5: "cm", 6: "m"}

CAPAS = {
    "lote": ("lote", "predio", "lindero", "parcela"),
    "ocupacion": ("ocupacion", "ocupación", "huella", "indice ocup"),
    "construccion": ("placa", "piso", "planta", "nivel", "area construida", "area-construida"),
    "cesion": ("cesion", "cesión", "zona verde", "espacio publico"),
    "via": ("via", "vía", "calzada", "anden", "andén"),
}


def _pares(ruta: Path):
    with open(ruta, encoding="utf-8", errors="replace") as f:
        lineas = f.read().splitlines()
    for i in range(0, len(lineas) - 1, 2):
        yield lineas[i].strip(), lineas[i + 1]


def _leer_propio(ruta: Path) -> dict:
    insunits = 0
    capas: set[str] = set()
    conteo: dict[str, int] = {}
    textos: list[dict] = []
    polis: list[dict] = []
    seccion = None
    ent = None          # entidad en curso
    pend = None         # código 9 de variable de encabezado
    pol_vieja = None    # POLYLINE en curso (con VERTEX)

    def cerrar(e):
        nonlocal pol_vieja
        if not e:
            return
        t = e["tipo"]
        conteo[t] = conteo.get(t, 0) + 1
        if t in ("TEXT", "MTEXT", "ATTRIB"):
            texto = re.sub(r"\\[A-Za-z][^;]*;|[{}]|\\P", " ", "".join(e.get("txt", [])))
            if texto.strip():
                textos.append({"texto": texto.strip(), "capa": e.get("capa", "0"), "x": e.get("x"), "y": e.get("y")})
        elif t == "LWPOLYLINE":
            if e.get("flag", 0) & 1 and len(e["pts"]) >= 3:
                polis.append({"capa": e.get("capa", "0"), "pts": e["pts"]})
        elif t == "POLYLINE":
            pol_vieja = {"capa": e.get("capa", "0"), "pts": [], "cerrada": bool(e.get("flag", 0) & 1)}
        elif t == "VERTEX" and pol_vieja is not None and "x" in e:
            pol_vieja["pts"].append((e["x"], e["y"]))
        elif t == "SEQEND" and pol_vieja is not None:
            if pol_vieja["cerrada"] and len(pol_vieja["pts"]) >= 3:
                polis.append({"capa": pol_vieja["capa"], "pts": pol_vieja["pts"]})
            pol_vieja = None

    for cod, val in _pares(ruta):
        if cod == "0":
            if val == "SECTION":
                seccion = "?"
                continue
            if val == "ENDSEC":
                cerrar(ent)
                ent, seccion = None, None
                continue
            if seccion == "ENTITIES" or seccion == "BLOCKS":
                cerrar(ent)
                ent = {"tipo": val, "pts": [], "txt": []} if seccion == "ENTITIES" else None
            elif seccion == "TABLES":
                ent = {"tipo": val}
            continue
        if seccion == "?" and cod == "2":
            seccion = val.strip()
            continue
        if seccion == "HEADER":
            if cod == "9":
                pend = val.strip()
            elif pend == "$INSUNITS" and cod == "70":
                insunits = int(val.strip() or 0)
            continue
        if seccion == "TABLES" and ent and ent["tipo"] == "LAYER" and cod == "2":
            capas.add(val.strip())
            continue
        if seccion != "ENTITIES" or ent is None:
            continue
        if cod == "8":
            ent["capa"] = val.strip()
        elif cod == "70":
            ent["flag"] = int(val.strip() or 0)
        elif cod in ("1", "3"):
            ent["txt"].append(val)
        elif cod == "10":
            ent["_x"] = float(val)
            if ent["tipo"] != "LWPOLYLINE":
                ent["x"] = float(val)
        elif cod == "20":
            y = float(val)
            if ent["tipo"] == "LWPOLYLINE" and "_x" in ent:
                ent["pts"].append((ent.pop("_x"), y))
            else:
                ent["y"] = y
    cerrar(ent)
    return {"insunits": insunits, "capas": sorted(capas), "conteo": conteo, "textos": textos, "polis": polis,
            "version": "lector propio"}


def _leer_ezdxf(ruta: Path) -> dict:
    import ezdxf
    doc = ezdxf.readfile(str(ruta))
    msp = doc.modelspace()
    conteo, textos, polis = {}, [], []
    for e in msp:
        t = e.dxftype()
        conteo[t] = conteo.get(t, 0) + 1
        if t == "TEXT":
            textos.append({"texto": e.dxf.text, "capa": e.dxf.layer, "x": e.dxf.insert.x, "y": e.dxf.insert.y})
        elif t == "MTEXT":
            textos.append({"texto": e.plain_text(), "capa": e.dxf.layer, "x": e.dxf.insert.x, "y": e.dxf.insert.y})
        elif t == "LWPOLYLINE" and e.closed:
            polis.append({"capa": e.dxf.layer, "pts": [(p[0], p[1]) for p in e.get_points("xy")]})
        elif t == "POLYLINE" and e.is_closed:
            polis.append({"capa": e.dxf.layer, "pts": [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]})
    return {"insunits": doc.header.get("$INSUNITS", 0), "capas": sorted(l.dxf.name for l in doc.layers),
            "conteo": conteo, "textos": textos, "polis": polis, "version": f"ezdxf · DXF {doc.dxfversion}"}


def _clase_capa(capa: str) -> str | None:
    c = capa.lower().replace("_", " ").replace("-", " ")
    for clase, claves in CAPAS.items():
        if any(k in c for k in claves):
            return clase
    return None


def leer(ruta: Path) -> dict:
    ruta = Path(ruta)
    try:
        crudo = _leer_ezdxf(ruta)
    except Exception:
        crudo = _leer_propio(ruta)
    escala = ESCALA_AREA.get(int(crudo["insunits"] or 0), 1.0)
    areas_por_capa: dict[str, list[float]] = {}
    for p in crudo["polis"]:
        areas_por_capa.setdefault(p["capa"], []).append(area_poligono(p["pts"]) * escala)
    por_clase: dict[str, dict[str, float]] = {}
    for capa, areas in areas_por_capa.items():
        clase = _clase_capa(capa)
        if clase:
            por_clase.setdefault(clase, {})[capa] = sum(areas)
    # georreferencia: coordenadas en MAGNA-SIRGAS Origen Nacional (EPSG:9377) rondan x 4,5–5,5 M y y 1–2,5 M
    lote_pts = None
    for p in crudo["polis"]:
        if _clase_capa(p["capa"]) == "lote":
            lote_pts = p["pts"]
            break
    georef = bool(lote_pts) and all(4.0e6 < x < 5.9e6 and 1.0e6 < y < 3.0e6 for x, y in lote_pts)
    return {
        "unidades": NOMBRE_UNIDAD.get(int(crudo["insunits"] or 0), "otra"),
        "escala_area": escala,
        "capas": crudo["capas"] or sorted({p["capa"] for p in crudo["polis"]} | {t["capa"] for t in crudo["textos"]}),
        "entidades": crudo["conteo"],
        "textos": crudo["textos"],
        "areas_por_capa": {k: round(sum(v), 2) for k, v in areas_por_capa.items()},
        "areas_por_clase": por_clase,
        "lote_puntos": lote_pts,
        "georreferenciado": georef,
        "lector": crudo["version"],
    }
