"""Expedientes y trámites (módulo 2).

Un expediente agrupa el predio y el solicitante; dentro de él hay uno o
varios trámites (licencia, prórroga, concepto…). Todo cambio queda en la
auditoría con el valor anterior; al eliminar un trámite se guarda una copia
completa de lo eliminado.
"""
from __future__ import annotations

import json
from datetime import date

from core import auditoria, calendario, db
from core import parametros as P

ESQUEMA = """
CREATE TABLE IF NOT EXISTS expedientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    radicado TEXT UNIQUE NOT NULL,
    fecha_radicacion TEXT NOT NULL,
    solicitante TEXT NOT NULL,
    tipo_persona TEXT NOT NULL DEFAULT 'natural',      -- natural | juridica
    documento TEXT,
    telefono TEXT,
    correo TEXT,
    autoriza_notificacion_correo INTEGER NOT NULL DEFAULT 0,
    direccion TEXT,
    matricula TEXT,
    cedula_catastral TEXT,
    clase_suelo TEXT,                                   -- urbano | expansion | suburbano | rural
    poligono TEXT,                                      -- código del art. 138 (urbano/expansión)
    area_actividad TEXT,                                -- residencial | comercio_servicios | artesanal | uso_social_obligado
    estrato INTEGER,
    estado TEXT NOT NULL DEFAULT 'radicado',
    responsable TEXT,
    observaciones TEXT,
    creado_por TEXT NOT NULL,
    creado TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    actualizado TEXT
);

CREATE TABLE IF NOT EXISTS tramites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expediente_id INTEGER NOT NULL REFERENCES expedientes(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL,
    modalidad TEXT,
    fecha_radicacion TEXT NOT NULL,
    fecha_limite TEXT,                                  -- 45 días hábiles
    estado TEXT NOT NULL DEFAULT 'radicado',
    datos TEXT NOT NULL DEFAULT '{}',                   -- áreas, pisos, usos… (JSON)
    observaciones TEXT,
    creado_por TEXT NOT NULL,
    creado TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    actualizado TEXT
);
"""

CAMPOS_EXPEDIENTE = ["radicado", "fecha_radicacion", "solicitante", "tipo_persona", "documento", "telefono",
                     "correo", "autoriza_notificacion_correo", "direccion", "matricula", "cedula_catastral",
                     "clase_suelo", "poligono", "area_actividad", "estrato", "estado", "responsable",
                     "observaciones"]
CLASES_SUELO = ("urbano", "expansion", "suburbano", "rural")


def migrar():
    db.migrar(ESQUEMA)


# ----------------------------------------------------------------- catálogo
def tipos() -> dict:
    return P.valor("tramites.tipos")


def campos() -> dict:
    return P.valor("tramites.campos")


def estados() -> list[str]:
    return P.valor("tramites.general.estados")


# --------------------------------------------------------------- radicados
def siguiente_radicado(fecha: date | None = None) -> str:
    fecha = fecha or date.today()
    formato = P.valor("tramites.general.formato_radicado")
    dane = P.valor("tramites.general.codigo_dane")
    aa = f"{fecha.year % 100:02d}"
    prefijo = formato.split("{consecutivo")[0].format(dane=dane, aa=aa)
    filas = db.consultar("SELECT radicado FROM expedientes WHERE radicado LIKE ?", (prefijo + "%",))
    mayor = 0
    for f in filas:
        cola = f["radicado"][len(prefijo):]
        if cola.isdigit():
            mayor = max(mayor, int(cola))
    return formato.format(dane=dane, aa=aa, consecutivo=mayor + 1)


# -------------------------------------------------------------- expedientes
def crear(datos: dict, usuario: str) -> int:
    d = {k: datos.get(k) for k in CAMPOS_EXPEDIENTE if k in datos}
    if not d.get("radicado"):
        d["radicado"] = siguiente_radicado()
    if not d.get("solicitante"):
        raise ValueError("El solicitante es obligatorio.")
    d.setdefault("fecha_radicacion", date.today().isoformat())
    d.setdefault("estado", "radicado")
    if d.get("poligono"):
        d["poligono"] = d["poligono"].strip().upper()
    cols = ", ".join(d) + ", creado_por"
    eid = db.ejecutar(f"INSERT INTO expedientes ({cols}) VALUES ({', '.join('?' * (len(d) + 1))})",
                      (*d.values(), usuario))
    auditoria.registrar(usuario, "crear", "expediente", eid, despues=d)
    return eid


def obtener(eid: int) -> dict | None:
    f = db.consultar("SELECT * FROM expedientes WHERE id=?", (eid,))
    return f[0] if f else None


def editar(eid: int, cambios: dict, usuario: str, motivo: str | None = None) -> None:
    antes = obtener(eid)
    if not antes:
        raise KeyError(eid)
    cambios = {k: v for k, v in cambios.items() if k in CAMPOS_EXPEDIENTE and antes.get(k) != v}
    if not cambios:
        return
    if cambios.get("poligono"):
        cambios["poligono"] = cambios["poligono"].strip().upper()
    sets = ", ".join(f"{k}=?" for k in cambios)
    db.ejecutar(f"UPDATE expedientes SET {sets}, actualizado=datetime('now','localtime') WHERE id=?",
                (*cambios.values(), eid))
    auditoria.registrar(usuario, "editar", "expediente", eid,
                        antes={k: antes[k] for k in cambios}, despues=cambios, motivo=motivo)


def listar(texto: str = "", estado: str | None = None, tipo_tramite: str | None = None) -> list[dict]:
    sql = ("SELECT e.*, (SELECT COUNT(*) FROM tramites t WHERE t.expediente_id=e.id) AS n_tramites "
           "FROM expedientes e WHERE 1=1")
    params: list = []
    if texto:
        sql += (" AND (e.radicado LIKE ? OR e.solicitante LIKE ? OR e.matricula LIKE ? "
                "OR e.cedula_catastral LIKE ? OR e.direccion LIKE ? OR e.documento LIKE ?)")
        params += [f"%{texto}%"] * 6
    if estado:
        sql += " AND e.estado=?"
        params.append(estado)
    if tipo_tramite:
        sql += " AND EXISTS (SELECT 1 FROM tramites t WHERE t.expediente_id=e.id AND t.tipo=?)"
        params.append(tipo_tramite)
    return db.consultar(sql + " ORDER BY e.id DESC", params)


def eliminar_expediente(eid: int, usuario: str, motivo: str) -> None:
    exp = obtener(eid)
    if not exp:
        return
    copia = {"expediente": exp, "tramites": tramites(eid)}
    db.ejecutar("DELETE FROM expedientes WHERE id=?", (eid,))
    auditoria.registrar(usuario, "eliminar", "expediente", eid, antes=copia, motivo=motivo)


# ------------------------------------------------------------------ trámites
def _limite(fecha_radicacion: str) -> str:
    dias = P.valor("nacional.licencias.termino_resolver_dias_habiles")
    return calendario.sumar_dias_habiles(date.fromisoformat(fecha_radicacion), dias).isoformat()


def agregar_tramite(eid: int, tipo: str, modalidad: str | None, datos: dict, usuario: str,
                    fecha_radicacion: str | None = None, observaciones: str = "") -> int:
    if tipo not in tipos():
        raise ValueError(f"Tipo de trámite no válido: {tipo}")
    fr = fecha_radicacion or date.today().isoformat()
    tid = db.ejecutar(
        "INSERT INTO tramites (expediente_id, tipo, modalidad, fecha_radicacion, fecha_limite, datos, "
        "observaciones, creado_por) VALUES (?,?,?,?,?,?,?,?)",
        (eid, tipo, modalidad, fr, _limite(fr), json.dumps(datos, ensure_ascii=False, default=str),
         observaciones, usuario))
    auditoria.registrar(usuario, "crear", "tramite", tid,
                        despues={"expediente_id": eid, "tipo": tipo, "modalidad": modalidad, "datos": datos})
    return tid


def tramite(tid: int) -> dict | None:
    f = db.consultar("SELECT * FROM tramites WHERE id=?", (tid,))
    if not f:
        return None
    t = f[0]
    t["datos"] = json.loads(t["datos"] or "{}")
    return t


def tramites(eid: int) -> list[dict]:
    salida = []
    for t in db.consultar("SELECT * FROM tramites WHERE expediente_id=? ORDER BY id", (eid,)):
        t["datos"] = json.loads(t["datos"] or "{}")
        salida.append(t)
    return salida


def editar_tramite(tid: int, cambios: dict, usuario: str, motivo: str | None = None) -> None:
    antes = tramite(tid)
    if not antes:
        raise KeyError(tid)
    permitidos = {"modalidad", "estado", "datos", "observaciones", "fecha_radicacion"}
    cambios = {k: v for k, v in cambios.items() if k in permitidos and antes.get(k) != v}
    if not cambios:
        return
    valores = dict(cambios)
    if "datos" in valores:
        valores["datos"] = json.dumps(valores["datos"], ensure_ascii=False, default=str)
    if "fecha_radicacion" in valores:
        valores["fecha_limite"] = _limite(valores["fecha_radicacion"])
    sets = ", ".join(f"{k}=?" for k in valores)
    db.ejecutar(f"UPDATE tramites SET {sets}, actualizado=datetime('now','localtime') WHERE id=?",
                (*valores.values(), tid))
    auditoria.registrar(usuario, "editar", "tramite", tid,
                        antes={k: antes[k] for k in cambios}, despues=cambios, motivo=motivo)


def eliminar_tramite(tid: int, usuario: str, motivo: str) -> dict:
    """Elimina un trámite cargado por error. Guarda copia completa en auditoría."""
    if not motivo or len(motivo.strip()) < 5:
        raise ValueError("Escriba el motivo de la eliminación.")
    t = tramite(tid)
    if not t:
        raise KeyError(tid)
    db.ejecutar("DELETE FROM tramites WHERE id=?", (tid,))
    auditoria.registrar(usuario, "eliminar", "tramite", tid, antes=t, motivo=motivo)
    return t


def historial(eid: int) -> list[dict]:
    ids_t = [str(t["id"]) for t in tramites(eid)] or ["-1"]
    marca = f'%"expediente_id": {eid},%'
    sql = ("SELECT * FROM auditoria WHERE (entidad='expediente' AND entidad_id=?) "
           f"OR (entidad='tramite' AND (entidad_id IN ({','.join('?' * len(ids_t))}) "
           "OR despues LIKE ? OR antes LIKE ?)) ORDER BY id DESC")
    return db.consultar(sql, (str(eid), *ids_t, marca, marca))


def vencimientos(dias: int = 5) -> list[dict]:
    """Trámites abiertos cuyo término vence en los próximos `dias` hábiles o ya venció."""
    hoy = date.today()
    tope = calendario.sumar_dias_habiles(hoy, dias).isoformat()
    cerrados = ("licencia_expedida", "negado", "desistido", "archivado")
    return db.consultar(
        "SELECT t.*, e.radicado, e.solicitante FROM tramites t JOIN expedientes e ON e.id=t.expediente_id "
        f"WHERE t.estado NOT IN ({','.join('?' * len(cerrados))}) AND t.fecha_limite <= ? ORDER BY t.fecha_limite",
        (*cerrados, tope))
