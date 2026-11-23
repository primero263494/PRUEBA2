"""Despachador: identifica formato, nivel de lectura y disciplina de cada
archivo, y lo convierte en datos normalizados con evidencia.

Niveles:
  completa  — geometría o datos estructurados (DXF, DWG convertido, IFC,
              .e2k/.s2k/.f2k, Excel/CSV, AGS4, capas SIG)
  texto     — PDF digital o escaneado, imágenes, Word (texto por OCR local o IA)
  cerrado   — formato propietario sin lector abierto: se pide la exportación
"""
from __future__ import annotations

import re
from pathlib import Path

from core.planos import csi, dxf, ifc, tablas, texto
from core.planos.util import dato
from core.rutas import TEMP_DIR

COMPLETA = {"dxf", "dwg", "ifc", "e2k", "s2k", "f2k", "xlsx", "xls", "csv", "ags",
            "geojson", "json", "kml", "kmz", "gpkg", "shp", "zip"}
TEXTO = {"pdf", "png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp", "docx", "txt"}
CERRADOS = {
    "rvt": "Revit: pida el modelo en IFC (2x3 o 4) y los planos en PDF.",
    "rfa": "Familia de Revit: no aplica; pida IFC o PDF.",
    "skp": "SketchUp: pida DXF/DWG o IFC y PDF.",
    "pln": "ArchiCAD: pida IFC y PDF.",
    "edb": "ETABS (binario): pida el .e2k (File > Export > ETABS .e2k) y las tablas de derivas en Excel.",
    "sdb": "SAP2000 (binario): pida el .s2k (File > Export > SAP2000 .s2k) y tablas en Excel.",
    "fdb": "SAFE (binario): pida el .f2k y las tablas en Excel.",
    "cyp": "CYPECAD: pida IFC, planos en PDF/DXF y listados en Excel/PDF.",
    "rtd": "Robot: pida IFC y tablas en Excel.",
    "gpj": "gINT: pida el AGS4 o Excel de sondeos.",
    "dgn": "MicroStation: pida DXF/DWG.",
}
SIG = {"geojson", "json", "kml", "kmz", "gpkg", "shp", "zip"}


def nivel(ext: str) -> str:
    ext = ext.lower().strip(".")
    if ext in CERRADOS:
        return "cerrado"
    if ext in COMPLETA:
        return "completa"
    if ext in TEXTO:
        return "texto"
    return "desconocido"


def _num_piso(nombre: str) -> int | None:
    m = re.search(r"(?:piso|nivel|planta|placa|p)\s*[-_ ]?\s*(\d{1,2})", nombre.lower())
    return int(m.group(1)) if m else None


def _desde_dxf(d: dict, nombre: str) -> tuple[str, dict]:
    datos = {}
    cl = d["areas_por_clase"]
    if cl.get("lote"):
        capa, area = max(cl["lote"].items(), key=lambda kv: kv[1])
        datos["area_lote"] = dato(round(area, 2), f"{nombre} · polilínea cerrada en capa '{capa}'", "m²")
    if cl.get("ocupacion"):
        capa, area = max(cl["ocupacion"].items(), key=lambda kv: kv[1])
        datos["area_ocupada"] = dato(round(area, 2), f"{nombre} · capa '{capa}'", "m²")
    pisos = {}
    for capa, area in (cl.get("construccion") or {}).items():
        n = _num_piso(capa)
        if n:
            pisos[n] = pisos.get(n, 0) + area
    if pisos:
        datos["areas_por_piso"] = dato({str(k): round(v, 2) for k, v in sorted(pisos.items())},
                                       f"{nombre} · capas de placas/pisos", "m²")
        datos["area_construida"] = dato(round(sum(pisos.values()), 2), f"{nombre} · suma de capas por piso", "m²")
        datos["n_pisos"] = dato(len(pisos), f"{nombre} · capas por piso")
    if d["georreferenciado"]:
        datos["lote_puntos_9377"] = dato(d["lote_puntos"], f"{nombre} · lote en MAGNA-SIRGAS Origen Nacional")
    # cuadro de áreas y notas escritas en el plano
    escrito = texto.extraer("\n".join(t["texto"] for t in d["textos"]))
    for k, v in escrito.items():
        clave = k if k not in datos else f"{k}_texto"
        v["evidencia"] = f"{nombre} · texto del plano: {v['evidencia']}"
        datos[clave] = v
    disc = "estructural" if any("estruct" in c.lower() or "column" in c.lower() or "viga" in c.lower() for c in d["capas"]) \
        else "arquitectonico"
    if any(k in nombre.lower() for k in ("topo", "levantamiento")):
        disc = "topografico"
    return disc, datos


def analizar(ruta: Path, nombre: str | None = None, modo_lectura: str | None = None) -> dict:
    ruta = Path(ruta)
    nombre = nombre or ruta.name
    ext = ruta.suffix.lower().strip(".")
    res = {"archivo": nombre, "ruta": str(ruta), "formato": ext, "nivel": nivel(ext), "disciplina": "sin_clasificar",
           "datos": {}, "resumen": {}, "avisos": []}
    try:
        if ext in CERRADOS:
            res["avisos"].append(CERRADOS[ext])
            return res
        if ext == "dwg":
            from core import conversores
            conv = conversores.dwg_a_dxf(ruta, TEMP_DIR / "dwg")
            res["avisos"].append(f"DWG convertido a DXF con {conv['motor']}.")
            ruta, ext = Path(conv["dxf"]), "dxf"
        if ext == "dxf":
            d = dxf.leer(ruta)
            res["disciplina"], res["datos"] = _desde_dxf(d, nombre)
            res["resumen"] = {"lector": d["lector"], "unidades": d["unidades"], "capas": len(d["capas"]),
                              "entidades": sum(d["entidades"].values()), "textos": len(d["textos"]),
                              "areas_por_capa": d["areas_por_capa"], "georreferenciado": d["georreferenciado"]}
            if d["unidades"].startswith("sin unidad"):
                res["avisos"].append("El DXF no declara unidades ($INSUNITS); las áreas se calcularon asumiendo metros.")
            if not d["areas_por_clase"]:
                res["avisos"].append("No hay polilíneas cerradas en capas reconocibles (LOTE, OCUPACION, PISO 1…). "
                                     "Corrija los valores a mano o pida las capas con esos nombres.")
        elif ext == "ifc":
            d = ifc.leer(ruta)
            res["disciplina"] = d["disciplina"]
            ev = f"{nombre} · IFC {d['esquema']} ({d['lector']})"
            res["datos"]["n_pisos"] = dato(d["n_pisos"], ev + " · IfcBuildingStorey")
            if d["alturas_entrepiso"]:
                res["datos"]["alturas_entrepiso"] = dato(d["alturas_entrepiso"], ev + " · elevaciones de pisos", "m")
            if d["area_bruta_pisos"]:
                res["datos"]["area_construida"] = dato(d["area_bruta_pisos"], ev + " · GrossFloorArea", "m²")
            res["resumen"] = {"esquema": d["esquema"], "pisos": d["pisos"], "elementos": d["elementos"],
                              "espacios": len(d["espacios"])}
        elif ext in ("e2k", "s2k", "f2k"):
            d = csi.leer(ruta)
            res["disciplina"] = "estructural"
            ev = f"{nombre} · {d['formato']} ({d['unidades']})"
            res["datos"]["n_pisos"] = dato(d["n_pisos"], ev + " · STORY")
            if d["alturas_entrepiso"]:
                res["datos"]["alturas_entrepiso"] = dato(d["alturas_entrepiso"], ev + " · alturas de piso", "m")
            if d["fc_mpa"]:
                res["datos"]["fc_mpa"] = dato(min(d["fc_mpa"]), ev + f" · f'c de materiales {d['fc_mpa']}", "MPa")
            if d["fy_mpa"]:
                res["datos"]["fy_mpa"] = dato(max(d["fy_mpa"]), ev + f" · fy {d['fy_mpa']}", "MPa")
            res["resumen"] = {"materiales": d["materiales"], "conteo": d["conteo"], "cargas_sismicas": d["cargas_sismicas"]}
            if d["aviso"]:
                res["avisos"].append(d["aviso"])
            if not d["cargas_sismicas"]:
                res["avisos"].append("El modelo no tiene patrones de carga sísmica identificables.")
        elif ext in ("xlsx", "xls", "csv", "ags"):
            d = tablas.leer_ags(ruta) if ext == "ags" else tablas.leer(ruta)
            if d["deriva_max"] is not None:
                res["disciplina"] = "estructural"
                peor = max(d["derivas"], key=lambda x: x["valor"])
                res["datos"]["deriva_max"] = dato(round(d["deriva_max"], 5),
                                                  f"{nombre} · hoja {peor['hoja']}, columna '{peor['columna']}', piso {peor['piso']}",
                                                  "fracción de hpi")
            if d["n_sondeos"]:
                res["disciplina"] = "geotecnico"
                res["datos"]["n_sondeos"] = dato(d["n_sondeos"], f"{nombre} · {', '.join(map(str, d['sondeos'][:10]))}")
            if d["profundidad_max"] is not None:
                res["datos"]["profundidad_max_m"] = dato(d["profundidad_max"], f"{nombre} · profundidad máxima", "m")
            res["resumen"] = {"hojas": d["hojas"], "filas_deriva": len(d["derivas"]), "sondeos": d.get("sondeos")}
            if not res["datos"]:
                res["avisos"].append("No se reconocieron columnas de derivas ni de sondeos.")
        elif ext in SIG:
            res["disciplina"] = "sig"
            res["datos"]["geometria"] = dato(str(ruta), f"{nombre} · polígono para cruce con cartografía")
        elif ext in TEXTO:
            from core import lectura
            lec = lectura.leer(ruta, forzar_modo=modo_lectura)
            if lec.get("aviso"):
                res["avisos"].append(lec["aviso"])
            txt = lec["texto"]
            res["disciplina"] = texto.disciplina(txt, nombre)
            res["datos"] = {k: {**v, "evidencia": f"{nombre} · {v['evidencia']}"} for k, v in texto.extraer(txt).items()}
            res["resumen"] = {"metodo": lec["metodo"], "paginas": lec["paginas"], "caracteres": len(txt)}
            if len(txt.strip()) < 50:
                res["avisos"].append("Casi no se obtuvo texto: el escaneo puede ser de baja calidad. Pruebe el modo IA "
                                     "o escriba los valores a mano.")
        else:
            res["avisos"].append(f"Formato .{ext} sin lector.")
    except Exception as e:      # un archivo dañado no detiene el análisis de los demás
        res["avisos"].append(f"No se pudo leer: {e}")
    return res
