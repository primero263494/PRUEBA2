"""Gestión documental (módulo 3).

Los archivos se guardan organizados así:
    datos/expedientes/<radicado>/<id trámite>_<tipo trámite>/<tipo documento>/<archivo>
Si se sube otro archivo con el mismo nombre y tipo, se guarda como versión
nueva (_v2, _v3…) sin borrar la anterior. Al eliminar, el archivo pasa a
datos/papelera y queda registrado en auditoría con todos sus datos.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import unicodedata
from datetime import date
from pathlib import Path

from core import auditoria, db, expedientes as E
from core import parametros as P
from core.rutas import DATOS, EXPEDIENTES_DIR

PAPELERA = DATOS / "papelera"
PAPELERA.mkdir(parents=True, exist_ok=True)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS documentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expediente_id INTEGER NOT NULL REFERENCES expedientes(id) ON DELETE CASCADE,
    tramite_id INTEGER REFERENCES tramites(id) ON DELETE SET NULL,
    tipo_documento TEXT NOT NULL,
    nombre_original TEXT NOT NULL,
    archivo TEXT NOT NULL,
    extension TEXT NOT NULL,
    tamano INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    fecha_expedicion TEXT,
    observaciones TEXT,
    cargado_por TEXT NOT NULL,
    fecha TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""


def migrar():
    db.migrar(ESQUEMA)


# ------------------------------------------------------------------ catálogo
def catalogo() -> dict:
    return P.valor("tramites.documentos.catalogo")


def extensiones() -> list[str]:
    return P.valor("tramites.documentos.extensiones_permitidas")


def _plano(t: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")
    return re.sub(r"[_\-\.]+", " ", t)


def sugerir_tipo(nombre_archivo: str) -> str:
    """Clasificación automática por palabras del nombre del archivo."""
    nombre = " " + _plano(Path(nombre_archivo).stem) + " "
    ext = Path(nombre_archivo).suffix.lower().strip(".")
    mejor, puntaje = "otro", 0
    for clave, d in catalogo().items():
        for k in d.get("claves", []):
            kk = _plano(k)
            if kk.strip() and kk in nombre and len(kk) > puntaje:
                mejor, puntaje = clave, len(kk)
    if mejor == "otro" and ext in ("e2k", "s2k", "f2k"):
        return "memorias_calculo"
    if mejor == "otro" and ext in ("dwg", "dxf", "ifc"):
        return "planos_arquitectonicos"
    return mejor


def lista_secretaria(expediente: dict | None, tramite: dict) -> tuple[str, dict] | None:
    """Lista del listado de requisitos de la Secretaría que aplica al trámite (la primera que coincide)."""
    try:
        listas = P.valor("requisitos.listas")
    except KeyError:
        return None
    clase = (expediente or {}).get("clase_suelo") or ""
    for clave, l in listas.items():
        if tramite["tipo"] not in l["tipos"]:
            continue
        if l.get("modalidades") and tramite.get("modalidad") not in l["modalidades"]:
            continue
        if l.get("clase_suelo") and clase not in l["clase_suelo"]:
            continue
        return clave, l
    return None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _condicion(nombre: str, exp: dict, tr: dict) -> bool:
    d = tr.get("datos") or {}
    if nombre == "juridica":
        return exp.get("tipo_persona") == "juridica"
    if nombre in ("apoderado", "ph", "en_parcelacion"):
        return bool(d.get({"ph": "propiedad_horizontal"}.get(nombre, nombre)))
    if nombre == "lote_icanh":
        return (_num(d.get("area_lote")) or 0) >= P.valor("pbot.ambiental.arqueologia_preventiva_area_minima")
    if nombre == "urbano":
        return exp.get("clase_suelo") in ("urbano", "expansion")
    if nombre == "rural":
        return exp.get("clase_suelo") in ("rural", "suburbano")
    raise ValueError(f"Condición desconocida en requisitos_secretaria.yaml: {nombre}")


def _regla_suelos(regla: str, exp: dict, tr: dict) -> tuple[str, str]:
    """Estudio de suelos o apique según el listado de la Secretaría."""
    d = tr.get("datos") or {}
    pisos = _num(d.get("n_pisos"))
    if regla == "suelos_urbano":
        lim = P.valor("requisitos.criterios.urbano_pisos_estudio_suelos")
        if pisos is None or pisos == 0:
            return "estudio_suelos|apique", "Indique el número de pisos: 3 o más → estudio de suelos; 2 o menos → apique."
        return ("estudio_suelos", f"{pisos:g} pisos ≥ {lim}") if pisos >= lim else ("apique", f"{pisos:g} pisos < {lim}")
    area = _num(d.get("area_construida")) or 0
    lim_area = P.valor("requisitos.criterios.rural_area_estudio_suelos")
    motivos = []
    if area >= lim_area:
        motivos.append(f"área a construir {area:g} m² ≥ {lim_area:g}")
    if pisos and pisos >= 2 and d.get("mansarda"):
        motivos.append("dos niveles y mansarda")
    if pisos and pisos >= 3:
        motivos.append(f"{pisos:g} pisos")
    if d.get("en_parcelacion"):
        motivos.append("predio en parcelación")
    if d.get("propiedad_horizontal"):
        motivos.append("propiedad horizontal (si el reglamento lo establece)")
    if motivos:
        return "estudio_suelos", "; ".join(motivos)
    if pisos is None or pisos == 0:
        return "estudio_suelos|apique", "Indique pisos y área a construir para definir estudio o apique."
    return "apique", f"Casa de {pisos:g} piso(s) sin mansarda, área {area:g} m² < {lim_area:g}"


def requisitos(expediente: dict, tramite: dict) -> list[dict]:
    """Requisitos documentales del trámite: [{tipo, nombre, opcional, nota, fuente}].

    Usa el listado de requisitos de la Secretaría (requisitos_secretaria.yaml);
    si el trámite no está en el listado, usa el manual (tramites.yaml)."""
    cat = catalogo()
    encontrada = lista_secretaria(expediente, tramite)
    if encontrada is None:
        return [{"tipo": r, "nombre": " o ".join(cat[o]["nombre"] for o in r.split("|")), "opcional": False, "nota": "",
                 "fuente": P.obtener("tramites.documentos.requeridos_por_tipo").fuente}
                for r in _requeridos_manual(expediente, tramite)]
    clave, lista = encontrada
    fuente = f"{P.obtener('requisitos.listas').fuente} — {lista['titulo']}"
    salida = []
    for r in lista["requisitos"]:
        if r.get("cond") and not _condicion(r["cond"], expediente, tramite):
            continue
        doc, nota = r["doc"], r.get("nota", "")
        if r.get("regla"):
            doc, motivo = _regla_suelos(r["regla"], expediente, tramite)
            nota = f"{nota} {motivo}".strip()
            nombre = " o ".join(cat[o]["nombre"] for o in doc.split("|"))
        else:
            nombre = r.get("texto") or " o ".join(cat[o]["nombre"] for o in doc.split("|"))
        salida.append({"tipo": doc, "nombre": nombre, "opcional": bool(r.get("opcional")), "nota": nota, "fuente": fuente})
    # una misma clave no se repite
    vistos, unicos = set(), []
    for r in salida:
        if r["tipo"] not in vistos:
            vistos.add(r["tipo"])
            unicos.append(r)
    return unicos


def requeridos(expediente: dict, tramite: dict) -> list[str]:
    """Claves de los documentos obligatorios ('a|b' = cualquiera)."""
    return [r["tipo"] for r in requisitos(expediente, tramite) if not r["opcional"]]


def _requeridos_manual(expediente: dict, tramite: dict) -> list[str]:
    """Documentos exigidos según el manual de trámites (para trámites que no están en el listado)."""
    tipo = tramite["tipo"]
    base = (P.valor("tramites.documentos.base_reducida_prorroga") if tipo == "prorroga"
            else list(P.valor("tramites.documentos.base_comunes")))
    if tipo in ("concepto_norma", "concepto_uso", "alineamiento", "certificado_riesgo"):
        base = ["identificacion", "cert_tradicion"]
    req = base + list(P.valor("tramites.documentos.requeridos_por_tipo").get(tipo, []))
    if expediente.get("tipo_persona") == "juridica":
        req.append("camara_comercio")
    return list(dict.fromkeys(req))


# ------------------------------------------------------------------- rutas
def _seguro(nombre: str) -> str:
    base = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    base = re.sub(r"[^\w\.\-]+", "_", base).strip("._")
    return base or "archivo"


def _carpeta(expediente: dict, tramite: dict | None, tipo_doc: str) -> Path:
    exp = _seguro(expediente["radicado"])
    tr = f"{tramite['id']}_{tramite['tipo']}" if tramite else "general"
    return EXPEDIENTES_DIR / exp / tr / tipo_doc


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


# --------------------------------------------------------------- operaciones
def subir(origen: Path, expediente_id: int, tramite_id: int | None, tipo_documento: str | None,
          usuario: str, fecha_expedicion: str | None = None, observaciones: str = "",
          nombre_original: str | None = None) -> dict:
    origen = Path(origen)
    nombre_original = nombre_original or origen.name
    ext = origen.suffix.lower().strip(".")
    if ext not in extensiones():
        raise ValueError(f"Extensión .{ext} no permitida. Permitidas: {', '.join(extensiones())}")
    tam = origen.stat().st_size
    if tam > P.valor("tramites.documentos.tamano_maximo_mb") * 1024 * 1024:
        raise ValueError("El archivo supera el tamaño máximo permitido.")
    exp = E.obtener(expediente_id)
    if not exp:
        raise KeyError("Expediente no encontrado.")
    tr = E.tramite(tramite_id) if tramite_id else None
    tipo = tipo_documento or sugerir_tipo(nombre_original)
    if tipo not in catalogo():
        raise ValueError(f"Tipo de documento no válido: {tipo}")
    sha = _sha256(origen)
    repetido = db.consultar("SELECT id, nombre_original FROM documentos WHERE expediente_id=? AND sha256=?",
                            (expediente_id, sha))
    carpeta = _carpeta(exp, tr, tipo)
    carpeta.mkdir(parents=True, exist_ok=True)
    limpio = _seguro(nombre_original)
    previos = db.consultar("SELECT MAX(version) AS v FROM documentos WHERE expediente_id=? AND "
                           "IFNULL(tramite_id,0)=? AND tipo_documento=? AND nombre_original=?",
                           (expediente_id, tramite_id or 0, tipo, nombre_original))
    version = (previos[0]["v"] or 0) + 1
    destino = carpeta / (limpio if version == 1 else f"{Path(limpio).stem}_v{version}{Path(limpio).suffix}")
    shutil.copy2(origen, destino)
    did = db.ejecutar(
        "INSERT INTO documentos (expediente_id, tramite_id, tipo_documento, nombre_original, archivo, extension, "
        "tamano, sha256, version, fecha_expedicion, observaciones, cargado_por) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (expediente_id, tramite_id, tipo, nombre_original, str(destino), ext, tam, sha, version,
         fecha_expedicion, observaciones, usuario))
    auditoria.registrar(usuario, "cargar", "documento", did,
                        despues={"expediente_id": expediente_id, "tramite_id": tramite_id, "tipo": tipo,
                                 "archivo": nombre_original, "version": version, "sha256": sha})
    return {"id": did, "tipo": tipo, "version": version, "ruta": str(destino),
            "duplicado_de": repetido[0] if repetido else None}


def obtener(did: int) -> dict | None:
    f = db.consultar("SELECT * FROM documentos WHERE id=?", (did,))
    return f[0] if f else None


def listar(expediente_id: int, tramite_id: int | None = None) -> list[dict]:
    sql, params = "SELECT * FROM documentos WHERE expediente_id=?", [expediente_id]
    if tramite_id is not None:
        sql += " AND tramite_id=?"
        params.append(tramite_id)
    return db.consultar(sql + " ORDER BY tipo_documento, nombre_original, version", params)


def editar(did: int, cambios: dict, usuario: str) -> None:
    antes = obtener(did)
    permitidos = {"tipo_documento", "fecha_expedicion", "observaciones", "tramite_id"}
    cambios = {k: v for k, v in cambios.items() if k in permitidos and antes.get(k) != v}
    if not cambios:
        return
    if "tipo_documento" in cambios and cambios["tipo_documento"] not in catalogo():
        raise ValueError("Tipo de documento no válido.")
    # si cambia el tipo o el trámite, se mueve el archivo para mantener el orden
    if {"tipo_documento", "tramite_id"} & set(cambios):
        exp = E.obtener(antes["expediente_id"])
        tid = cambios.get("tramite_id", antes["tramite_id"])
        tr = E.tramite(tid) if tid else None
        carpeta = _carpeta(exp, tr, cambios.get("tipo_documento", antes["tipo_documento"]))
        carpeta.mkdir(parents=True, exist_ok=True)
        nuevo = carpeta / Path(antes["archivo"]).name
        shutil.move(antes["archivo"], nuevo)
        cambios["archivo"] = str(nuevo)
    sets = ", ".join(f"{k}=?" for k in cambios)
    db.ejecutar(f"UPDATE documentos SET {sets} WHERE id=?", (*cambios.values(), did))
    auditoria.registrar(usuario, "editar", "documento", did, antes={k: antes[k] for k in cambios}, despues=cambios)


def eliminar(did: int, usuario: str, motivo: str) -> dict:
    if not motivo or len(motivo.strip()) < 5:
        raise ValueError("Escriba el motivo de la eliminación.")
    d = obtener(did)
    if not d:
        raise KeyError(did)
    destino = PAPELERA / f"{date.today().isoformat()}_doc{did}_{Path(d['archivo']).name}"
    if Path(d["archivo"]).exists():
        shutil.move(d["archivo"], destino)
    db.ejecutar("DELETE FROM documentos WHERE id=?", (did,))
    auditoria.registrar(usuario, "eliminar", "documento", did, antes={**d, "papelera": str(destino)}, motivo=motivo)
    return {**d, "papelera": str(destino)}


def faltantes(expediente: dict, tramite: dict) -> list[dict]:
    """Compara lo exigido con lo cargado. Una alternativa 'a|b' se cumple con cualquiera. Incluye los opcionales (opcional=True)."""
    cargados = {d["tipo_documento"] for d in listar(expediente["id"], tramite["id"])}
    cargados |= {d["tipo_documento"] for d in listar(expediente["id"]) if d["tramite_id"] is None}
    return [{**r, "cargado": any(o in cargados for o in r["tipo"].split("|"))} for r in requisitos(expediente, tramite)]


def vencidos(expediente: dict, tramite: dict) -> list[dict]:
    """Documentos con vigencia (p. ej. 30 días) expedidos antes de lo permitido respecto a la radicación."""
    cat = catalogo()
    fr = date.fromisoformat(tramite["fecha_radicacion"][:10])
    salida = []
    for d in listar(expediente["id"], tramite["id"]):
        vig = cat.get(d["tipo_documento"], {}).get("vigencia_dias")
        if vig and d["fecha_expedicion"]:
            edad = (fr - date.fromisoformat(d["fecha_expedicion"][:10])).days
            if edad > vig or edad < 0:
                salida.append({**d, "edad_dias": edad, "vigencia_dias": vig})
    return salida


def carpeta_a_papelera(expediente: dict) -> str | None:
    """Mueve la carpeta de archivos de un expediente a la papelera (al eliminar el expediente)."""
    origen = EXPEDIENTES_DIR / _seguro(expediente["radicado"])
    if not origen.exists():
        return None
    destino = PAPELERA / f"{date.today().isoformat()}_exp{expediente['id']}_{origen.name}"
    shutil.move(str(origen), destino)
    return str(destino)


def fecha_documento(tramite_id: int, tipo: str) -> str | None:
    """Fecha de expedición más reciente de un tipo de documento del trámite (la usa la verificación)."""
    f = db.consultar("SELECT MAX(fecha_expedicion) AS f FROM documentos WHERE tramite_id=? AND tipo_documento=?",
                     (tramite_id, tipo))
    return f[0]["f"] if f else None
