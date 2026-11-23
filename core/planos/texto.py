"""Extracción de datos desde texto (PDF digital, OCR local o IA): memorias
estructurales, estudios de suelos, cuadros de áreas y rótulos de planos.

Cada hallazgo guarda el fragmento de texto donde se encontró (evidencia),
para que el revisor lo confirme. Lo que no se encuentra queda vacío; nunca
se completa con supuestos.
"""
from __future__ import annotations

import re
import unicodedata

from core.planos.util import dato, num

NUM = r"(-?\d[\d.,]*)"


def _plano(t: str) -> str:
    t = t.replace("\u2019", "'").replace("\u00b4", "'").replace("´", "'")
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    return re.sub(r"[ \t]+", " ", t)


def _buscar(texto: str, patron: str, grupo: int = 1, flags=re.IGNORECASE):
    m = re.search(patron, texto, flags)
    if not m:
        return None, None
    ini, fin = max(0, m.start() - 40), min(len(texto), m.end() + 40)
    return m.group(grupo), texto[ini:fin].replace("\n", " ").strip()


def _a_mpa(valor: float, unidad: str) -> float:
    u = (unidad or "").lower().replace(" ", "")
    if "psi" in u:
        return round(valor * 0.00689476, 2)
    if "kg" in u:
        return round(valor * 0.0980665, 2)
    if "kpa" in u:
        return round(valor / 1000, 2)
    return valor


DISCIPLINAS = {
    "estructural": ("memoria de calculo", "analisis sismico", "nsr-10", "deriva", "cortante basal", "despiece", "f'c",
                    "fy", "coeficiente de capacidad de disipacion", "sistema estructural", "titulo c"),
    "geotecnico": ("estudio de suelos", "estudio geotecnico", "sondeo", "perforacion", "capacidad portante",
                   "nivel freatico", "spt", "titulo h", "estratigraf", "apique"),
    "arquitectonico": ("cuadro de areas", "area construida", "planta arquitectonica", "fachada", "indice de ocupacion",
                       "area del lote", "corte arquitectonico"),
    "ambiental": ("cornare", "ronda hidrica", "vertimiento", "plan de manejo ambiental", "retiro a fuente"),
    "topografico": ("levantamiento topografico", "magna", "coordenadas", "cotas de nivel", "curvas de nivel"),
}


def disciplina(texto: str, nombre_archivo: str = "") -> str:
    t = _plano((texto[:60000] + " " + nombre_archivo).lower())
    puntajes = {d: sum(t.count(k) for k in claves) for d, claves in DISCIPLINAS.items()}
    mejor = max(puntajes, key=puntajes.get)
    return mejor if puntajes[mejor] > 0 else "sin_clasificar"


def extraer(texto: str) -> dict:
    t = _plano(texto)
    d: dict = {}

    def poner(clave, patron, conv=num, unidad="", grupo=1):
        v, ev = _buscar(t, patron, grupo)
        if v is not None:
            val = conv(v) if conv else v
            if val is not None:
                d[clave] = dato(val, ev, unidad)

    # --- sísmica y estructura
    poner("Aa", r"\bA\s*a\s*[=:]\s*(0[.,]\d+)")
    poner("Av", r"\bA\s*v\s*[=:]\s*(0[.,]\d+)")
    poner("Fa", r"\bF\s*a\s*[=:]\s*(\d[.,]\d+)")
    poner("Fv", r"\bF\s*v\s*[=:]\s*(\d[.,]\d+)")
    poner("I", r"(?:coeficiente de importancia|\bI)\s*[=:]\s*(1[.,]\d+)")
    poner("R0", r"\bR\s*[o0]\s*[=:]\s*(\d+[.,]?\d*)")
    poner("R", r"\bR\s*=\s*(\d+[.,]?\d*)")
    poner("perfil_suelo", r"perfil\s+(?:de\s+suelo\s+)?(?:tipo\s+)?([A-F])\b", conv=lambda x: x.upper())
    poner("grupo_uso", r"grupo\s+de\s+uso\s*[:=]?\s*(IV|III|II|I)\b", conv=lambda x: x.upper())
    poner("sistema_estructural", r"sistema\s+estructural\s*(?:de\s+)?[:=]?\s*([A-Za-z ]{6,60}?)(?:[.,;\n]|$)", conv=lambda x: x.strip())
    m = re.search(r"f\s*'?\s*c\s*[=:]\s*" + NUM + r"\s*(MPa|kg/cm2|kgf/cm2|kg/cm²|psi|kPa)", t, re.IGNORECASE)
    if m:
        d["fc_mpa"] = dato(_a_mpa(num(m.group(1)), m.group(2)), t[max(0, m.start() - 30):m.end() + 30], "MPa")
    m = re.search(r"\bf\s*y\s*[=:]\s*" + NUM + r"\s*(MPa|kg/cm2|kgf/cm2|kg/cm²|psi|kPa)", t, re.IGNORECASE)
    if m:
        d["fy_mpa"] = dato(_a_mpa(num(m.group(1)), m.group(2)), t[max(0, m.start() - 30):m.end() + 30], "MPa")
    m = re.search(r"deriva[^\n%]{0,60}?(\d+[.,]\d+)\s*%", t, re.IGNORECASE)
    if m:
        d["deriva_max"] = dato(round(num(m.group(1)) / 100, 6), t[max(0, m.start() - 20):m.end() + 20], "fracción de hpi")

    # --- geotecnia
    m = re.search(r"capacidad\s+(?:portante|admisible|de\s+carga)[^\n]{0,60}?" + NUM + r"\s*(kPa|kN/m2|kN/m²|t/m2|ton/m2|t/m²|kg/cm2)",
                  t, re.IGNORECASE)
    if m:
        v, u = num(m.group(1)), m.group(2).lower()
        kpa = v * 9.80665 if u.startswith("t") else v * 98.0665 if "kg" in u else v
        d["capacidad_portante_kpa"] = dato(round(kpa, 1), t[max(0, m.start() - 20):m.end() + 20], "kPa")
    if re.search(r"no\s+se\s+(?:encontro|detecto|registro)\s+(?:el\s+)?nivel\s+freatico", t, re.IGNORECASE):
        d["nivel_freatico_m"] = dato("no encontrado", "No se encontró nivel freático")
    else:
        poner("nivel_freatico_m", r"nivel\s+freatico[^\n]{0,50}?" + NUM + r"\s*m\b", unidad="m")
    poner("n_sondeos", r"(\d+)\s+(?:sondeos|perforaciones|apiques)", conv=lambda x: int(num(x)))
    poner("profundidad_max_m", r"profundidad\s+(?:maxima\s+)?(?:explorada\s+)?(?:de\s+)?" + NUM + r"\s*m\b", unidad="m")
    poner("cota_fundacion_m", r"(?:cota|profundidad)\s+de\s+(?:fundacion|desplante|cimentacion)[^\n]{0,30}?" + NUM + r"\s*m\b", unidad="m")
    poner("tipo_cimentacion", r"cimentacion\s+(?:recomendada\s+)?(?:tipo\s+|en\s+|con\s+|mediante\s+)?"
                              r"(zapatas?[^\n.,;]{0,40}|pilotes?[^\n.,;]{0,40}|losa[^\n.,;]{0,40}|vigas?\s+de\s+cimentacion[^\n.,;]{0,30}|caissons?[^\n.,;]{0,30})",
          conv=lambda x: x.strip())

    # --- cuadro de áreas (arquitectura)
    poner("area_lote", r"area\s+(?:del\s+|de\s+)?(?:lote|predio|terreno)\s*(?:bruta)?\s*[:=]?\s*" + NUM + r"\s*m", unidad="m²")
    poner("area_ocupada", r"area\s+(?:ocupada|de\s+ocupacion|primer\s+piso|en\s+primer\s+piso)\s*[:=]?\s*" + NUM + r"\s*m", unidad="m²")
    poner("area_construida", r"area\s+(?:total\s+)?construida\s*(?:total)?\s*[:=]?\s*" + NUM + r"\s*m", unidad="m²")
    poner("area_neta", r"area\s+neta\s*(?:urbanizable)?\s*[:=]?\s*" + NUM + r"\s*m", unidad="m²")
    poner("area_util", r"area\s+util\s*[:=]?\s*" + NUM + r"\s*m", unidad="m²")
    poner("io_declarado", r"indice\s+de\s+ocupacion\s*(?:\(?IO\)?)?\s*[:=]?\s*" + NUM + r"\s*(%)?",
          conv=lambda x: (num(x) / 100 if num(x) and num(x) > 1 else num(x)))
    poner("ic_declarado", r"indice\s+de\s+construccion\s*(?:\(?IC\)?)?\s*[:=]?\s*" + NUM)
    poner("n_pisos", r"(\d{1,2})\s+(?:pisos|niveles)\b", conv=lambda x: int(num(x)))
    poner("n_viviendas", r"(\d{1,4})\s+(?:viviendas|apartamentos|unidades\s+de\s+vivienda)\b", conv=lambda x: int(num(x)))
    poner("altura_entrepiso_m", r"altura\s+(?:de\s+)?entrepiso\s*[:=]?\s*" + NUM + r"\s*m", unidad="m")

    # --- firmas y profesionales
    mps = re.findall(r"(?:M\.?\s?P\.?|matricula\s+profesional|T\.?\s?P\.?)\s*(?:No\.?|N[°º]|#)?\s*[:.]?\s*([A-Z]{0,2}[0-9]{4,}[0-9A-Z\-]*)", t, re.IGNORECASE)
    if mps:
        d["matriculas_profesionales"] = dato(sorted(set(mps)), "Matrículas encontradas en el texto")
    return d
