"""Cartografía: carga de capas del PBOT y de Cornare, y cruce del predio.

Formatos vectoriales: Shapefile (.zip o .shp+.shx+.dbf+.prj), GeoJSON,
KML/KMZ, GeoPackage. Raster: GeoTIFF (DEM para pendientes). PDF e imágenes
se guardan como referencia visual (sin análisis espacial).

Cada capa se carga con un ROL. El cruce del predio usa el rol, no el
nombre del archivo, así que puede cargar la cartografía en cualquier
momento y el análisis la toma automáticamente.
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from core import auditoria, db
from core.rutas import CAPAS_DIR

# rol -> (descripción, plano PBOT de referencia)
ROLES = {
    "perimetro_urbano": ("Perímetro urbano y sanitario", "CG_017 / CG_018"),
    "clasificacion_suelo": ("Clasificación del suelo (urbano, expansión, rural, suburbano)", "CG_003 / CG_004 / CG_016"),
    "tratamientos": ("Polígonos de tratamiento (S1-CN-1, S3-DE-8…)", "Componente urbano"),
    "usos_suelo": ("Áreas de actividad / usos", "Componente urbano y rural"),
    "amenaza_movimiento_masa": ("Amenaza por movimiento en masa", "CG_007 / D_014"),
    "amenaza_inundacion": ("Amenaza por inundación", "CG_008 / D_015"),
    "amenaza_avenida_torrencial": ("Amenaza por avenida torrencial", "CG_009"),
    "riesgo": ("Zonas de riesgo (incluye alto no mitigable)", "CG_007 a CG_009"),
    "aptitud_geologica": ("Aptitud geológica", "CG_010 / CG_011"),
    "rondas_hidricas": ("Rondas hídricas / retiros a fuentes (Cornare 251/2011)", "EEP"),
    "mancha_inundacion_tr100": ("Mancha de inundación TR100 (La Cimarronas)", "Estudio hidrológico"),
    "areas_protegidas": ("Áreas protegidas SIRAP (RFPR, DRMI)", "Cornare"),
    "estructura_ecologica": ("Estructura Ecológica Principal", "CG EEP"),
    "pendientes": ("Pendientes / DEM", "Cornare / IGAC"),
    "patrimonio": ("BIC, centro histórico, áreas arqueológicas", "Sistema de patrimonio"),
    "plan_vial": ("Plan vial / vías obligadas", "CG_014 / CG_015"),
    "redes_servicios": ("Redes primarias y PTAR", "Sistema de servicios públicos"),
    "predios": ("Predios catastrales", "Catastro Antioquia"),
    "otra": ("Otra capa de referencia", ""),
}

EXT_VECTOR = {".geojson", ".json", ".kml", ".kmz", ".gpkg", ".shp", ".zip"}
EXT_RASTER = {".tif", ".tiff"}
EXT_REFERENCIA = {".pdf", ".png", ".jpg", ".jpeg"}

# CRS oficial: MAGNA-SIRGAS / Origen Nacional (EPSG:9377)
CRS_TRABAJO = "EPSG:9377"


def _gpd():
    try:
        import geopandas as gpd
        return gpd
    except ImportError as e:
        raise RuntimeError("Falta geopandas. Ejecute 'instalar.bat' o pip install geopandas.") from e


def _ruta_vector(carpeta: Path) -> Path | None:
    for ext in (".gpkg", ".geojson", ".json", ".shp", ".kml"):
        hallados = sorted(carpeta.rglob(f"*{ext}"))
        if hallados:
            return hallados[0]
    return None


def preparar_archivos(archivos: list[Path], carpeta: Path) -> Path:
    """Copia los archivos subidos; descomprime .zip/.kmz. Devuelve el archivo principal."""
    carpeta.mkdir(parents=True, exist_ok=True)
    for a in archivos:
        a = Path(a)
        if a.suffix.lower() in {".zip", ".kmz"}:
            with zipfile.ZipFile(a) as z:
                z.extractall(carpeta)
        else:
            shutil.copy2(a, carpeta / a.name)
    principal = _ruta_vector(carpeta)
    if principal:
        if principal.suffix.lower() == ".shp":
            faltan = [e for e in (".shx", ".dbf") if not principal.with_suffix(e).exists()]
            if faltan:
                raise ValueError(f"Al shapefile le faltan: {', '.join(faltan)}. Súbalos juntos o en un .zip.")
        return principal
    for ext in EXT_RASTER | EXT_REFERENCIA:
        hallados = sorted(carpeta.rglob(f"*{ext}"))
        if hallados:
            return hallados[0]
    raise ValueError("No se encontró un archivo de cartografía reconocible.")


def cargar_capa(archivos: list[Path], nombre: str, rol: str, fuente: str,
                campo_clave: str | None, usuario: str) -> dict:
    if rol not in ROLES:
        raise ValueError(f"Rol no válido: {rol}")
    cid = db.ejecutar(
        "INSERT INTO capas (nombre, rol, archivo, formato, fuente, campo_clave, cargado_por) VALUES (?,?,?,?,?,?,?)",
        (nombre, rol, "", "", fuente, campo_clave, usuario))
    carpeta = CAPAS_DIR / str(cid)
    try:
        principal = preparar_archivos(archivos, carpeta)
        ext = principal.suffix.lower()
        crs, n, formato = None, None, ext.strip(".")
        if ext in {".gpkg", ".geojson", ".json", ".shp", ".kml"}:
            gdf = _gpd().read_file(principal)
            n = len(gdf)
            crs = gdf.crs.to_string() if gdf.crs else None
            if crs is None:
                raise ValueError("La capa no trae sistema de coordenadas (.prj). Pida el archivo con su .prj.")
            if campo_clave and campo_clave not in gdf.columns:
                raise ValueError(f"El campo '{campo_clave}' no existe. Campos: {', '.join(map(str, gdf.columns))}")
        elif ext in EXT_RASTER:
            formato = "geotiff"
        else:
            formato = "referencia"
        db.ejecutar("UPDATE capas SET archivo=?, formato=?, crs=?, n_elementos=? WHERE id=?",
                    (str(principal), formato, crs, n, cid))
    except Exception:
        db.ejecutar("DELETE FROM capas WHERE id=?", (cid,))
        shutil.rmtree(carpeta, ignore_errors=True)
        raise
    auditoria.registrar(usuario, "cargar", "capa", cid,
                        despues={"nombre": nombre, "rol": rol, "formato": formato, "crs": crs, "elementos": n})
    return {"id": cid, "formato": formato, "crs": crs, "elementos": n}


def listar() -> list[dict]:
    return db.consultar("SELECT * FROM capas ORDER BY rol, nombre")


def capas_por_rol() -> dict[str, list[dict]]:
    salida: dict[str, list[dict]] = {}
    for c in listar():
        salida.setdefault(c["rol"], []).append(c)
    return salida


def roles_faltantes(requeridos=("clasificacion_suelo", "tratamientos", "amenaza_movimiento_masa",
                                "amenaza_inundacion", "rondas_hidricas", "areas_protegidas")) -> list[str]:
    cargados = capas_por_rol()
    return [r for r in requeridos if r not in cargados]


def eliminar(cid: int, usuario: str, motivo: str) -> None:
    fila = db.consultar("SELECT * FROM capas WHERE id=?", (cid,))
    if not fila:
        return
    db.ejecutar("DELETE FROM capas WHERE id=?", (cid,))
    shutil.rmtree(CAPAS_DIR / str(cid), ignore_errors=True)
    auditoria.registrar(usuario, "eliminar", "capa", cid, antes=fila[0], motivo=motivo)


def leer_predio(archivos: list[Path]):
    """Lee la geometría del predio (o proyecto) desde cualquier formato vectorial."""
    gpd = _gpd()
    carpeta = CAPAS_DIR / "_predio_tmp"
    shutil.rmtree(carpeta, ignore_errors=True)
    principal = preparar_archivos(archivos, carpeta)
    gdf = gpd.read_file(principal)
    if gdf.crs is None:
        raise ValueError("El predio no trae sistema de coordenadas.")
    return gdf


def cruzar_predio(predio_gdf, roles: list[str] | None = None) -> list[dict]:
    """Cruza el predio con todas las capas vectoriales cargadas.

    Devuelve por capa: área de intersección (m²), % del predio y los valores
    del campo clave (p. ej. código de tratamiento o nivel de amenaza).
    """
    gpd = _gpd()
    predio = predio_gdf.to_crs(CRS_TRABAJO)
    geom = predio.union_all() if hasattr(predio, "union_all") else predio.unary_union
    area_predio = geom.area
    resultados = []
    for capa in listar():
        if capa["formato"] in ("geotiff", "referencia"):
            continue
        if roles and capa["rol"] not in roles:
            continue
        gdf = gpd.read_file(capa["archivo"]).to_crs(CRS_TRABAJO)
        candidatos = gdf[gdf.intersects(geom)]
        filas = []
        for _, f in candidatos.iterrows():
            inter = f.geometry.intersection(geom)
            if inter.is_empty:
                continue
            filas.append({
                "valor": str(f[capa["campo_clave"]]) if capa["campo_clave"] else "",
                "area_m2": round(inter.area, 2),
                "porcentaje": round(100 * inter.area / area_predio, 2) if area_predio else None,
                "atributos": {k: (None if v is None else str(v)) for k, v in f.drop(labels="geometry").items()},
            })
        resultados.append({
            "capa": capa["nombre"], "rol": capa["rol"], "rol_descripcion": ROLES[capa["rol"]][0],
            "fuente": capa["fuente"], "afecta": bool(filas), "intersecciones": filas,
        })
    return resultados


def area_perimetro(gdf) -> dict:
    g = gdf.to_crs(CRS_TRABAJO)
    geom = g.union_all() if hasattr(g, "union_all") else g.unary_union
    return {"area_m2": round(geom.area, 2), "perimetro_m": round(geom.length, 2), "crs": CRS_TRABAJO}
