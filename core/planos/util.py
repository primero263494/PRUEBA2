"""Utilidades comunes de los lectores."""
from __future__ import annotations

import re


def num(texto) -> float | None:
    """Convierte '1.234,56', '1234.56', '1,234.56' o '27,5' en número."""
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    t = str(texto).strip().replace(" ", "").replace(" ", "")
    m = re.search(r"-?\d[\d.,]*", t)
    if not m:
        return None
    t = m.group(0).rstrip(".,")
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):      # 1.234,56
            t = t.replace(".", "").replace(",", ".")
        else:                                # 1,234.56
            t = t.replace(",", "")
    elif "," in t:
        partes = t.split(",")
        t = t.replace(",", ".") if len(partes) == 2 and len(partes[1]) != 3 else t.replace(",", "")
    elif t.count(".") > 1:
        t = t.replace(".", "")
    elif "." in t:
        ent, dec = t.split(".")
        if len(dec) == 3 and len(ent) <= 3 and ent not in ("0", "-0"):   # 1.234 = mil doscientos…
            t = ent + dec
    try:
        return float(t)
    except ValueError:
        return None


def area_poligono(puntos: list[tuple[float, float]]) -> float:
    """Fórmula del área de Gauss (shoelace)."""
    n = len(puntos)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = puntos[i]
        x2, y2 = puntos[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def dato(valor, evidencia: str, unidad: str = "") -> dict:
    return {"valor": valor, "unidad": unidad, "evidencia": evidencia}
