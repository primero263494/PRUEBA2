"""Listas de chequeo por trámite (módulo 5).

La lista se arma con las secciones que aplican al tipo de trámite
(listas_chequeo.yaml) más los documentos exigidos (tramites.yaml). Cada ítem
se marca cumple / no cumple / no aplica con observación. El programa propone
un estado a partir de la verificación automática y de los documentos
cargados, pero solo el revisor lo confirma.
"""
from __future__ import annotations

from core import auditoria, db, documentos as D, expedientes as E, verificacion as V
from core import parametros as P

# Ítems de verificación que, si no aparecen, significan que la condición no se da
NO_APLICA_SI_AUSENTE = {"Plan parcial", "Arqueología preventiva", "Antigüedad de la edificación",
                        "Oportunidad de la prórroga", "Número de predios"}

ESTADOS = ("pendiente", "cumple", "no_cumple", "no_aplica")
ETIQUETAS = {"pendiente": "Pendiente", "cumple": "Cumple", "no_cumple": "No cumple", "no_aplica": "No aplica"}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS chequeo_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tramite_id INTEGER NOT NULL REFERENCES tramites(id) ON DELETE CASCADE,
    item_id TEXT NOT NULL,
    seccion TEXT NOT NULL,
    orden INTEGER NOT NULL,
    texto TEXT NOT NULL,
    fuente TEXT,
    estado TEXT NOT NULL DEFAULT 'pendiente',
    observacion TEXT,
    revisor TEXT,
    fecha TEXT,
    UNIQUE (tramite_id, item_id)
);
CREATE TABLE IF NOT EXISTS chequeo_paquete (
    tramite_id INTEGER PRIMARY KEY REFERENCES tramites(id) ON DELETE CASCADE,
    completo INTEGER NOT NULL DEFAULT 0,
    fecha_completo TEXT,            -- fecha en que el paquete quedó completo para revisión
    observacion TEXT,
    usuario TEXT,
    fecha TEXT
);
"""


def migrar():
    db.migrar(ESQUEMA)


def _plantilla(expediente: dict, tramite: dict) -> list[dict]:
    secciones = P.valor("listas.secciones")
    orden_sec = P.valor("listas.secciones_por_tipo").get(tramite["tipo"], ["documentos"])
    items, n = [], 0
    for sec in orden_sec:
        if sec == "documentos":
            for req in D.requisitos(expediente, tramite):
                n += 1
                texto = f"Documento{' (si aplica)' if req['opcional'] else ''}: {req['nombre']}"
                if req["nota"]:
                    texto += f" — {req['nota']}"
                items.append({"item_id": f"doc:{req['tipo']}", "seccion": sec, "orden": n, "texto": texto,
                              "fuente": req["fuente"], "auto": f"doc:{req['tipo']}", "opcional": req["opcional"]})
            continue
        for it in secciones[sec]["items"]:
            if it.get("solo") and tramite["tipo"] not in it["solo"]:
                continue
            n += 1
            items.append({"item_id": it["id"], "seccion": sec, "orden": n, "texto": it["texto"],
                          "fuente": it.get("fuente", ""), "auto": it.get("auto")})
    return items


def generar(tramite_id: int) -> int:
    """Crea los ítems que falten y actualiza texto y orden de los existentes (sin tocar su estado).
    Los documentos que dejaron de exigirse (p. ej. cambió el número de pisos) se quitan si estaban pendientes.
    Devuelve cuántos agregó."""
    tr = E.tramite(tramite_id)
    exp = E.obtener(tr["expediente_id"])
    plantilla = _plantilla(exp, tr)
    actuales = {r["item_id"]: r for r in db.consultar("SELECT * FROM chequeo_items WHERE tramite_id=?", (tramite_id,))}
    existentes = set(actuales)
    ids = {i["item_id"] for i in plantilla}
    nuevos = [i for i in plantilla if i["item_id"] not in existentes]
    with db.conexion() as con:
        for iid, r in actuales.items():
            if iid.startswith("doc:") and iid not in ids and r["estado"] == "pendiente":
                con.execute("DELETE FROM chequeo_items WHERE id=?", (r["id"],))
        for i in plantilla:
            if i["item_id"] in actuales:
                con.execute("UPDATE chequeo_items SET texto=?, orden=?, fuente=? WHERE tramite_id=? AND item_id=?",
                            (i["texto"], i["orden"], i["fuente"], tramite_id, i["item_id"]))
        con.executemany(
            "INSERT INTO chequeo_items (tramite_id, item_id, seccion, orden, texto, fuente) VALUES (?,?,?,?,?,?)",
            [(tramite_id, i["item_id"], i["seccion"], i["orden"], i["texto"], i["fuente"]) for i in nuevos])
    return len(nuevos)


def sugerencias(tramite_id: int) -> dict[str, tuple[str, str]]:
    """item_id -> (estado sugerido, motivo)."""
    tr = E.tramite(tramite_id)
    exp = E.obtener(tr["expediente_id"])
    ver = {r["item"]: r for r in V.verificar(exp, tr)}
    docs = {x["tipo"]: x["cargado"] for x in D.faltantes(exp, tr)}
    mapa = {V.CUMPLE: "cumple", V.NO_CUMPLE: "no_cumple"}
    salida = {}
    for i in _plantilla(exp, tr):
        auto = i.get("auto") or ""
        if auto.startswith("doc:"):
            req = auto[4:]
            if docs.get(req):
                salida[i["item_id"]] = ("cumple", "Documento cargado")
        elif auto.startswith("verificacion:"):
            nombre = auto.split(":", 1)[1]
            r = ver.get(nombre)
            if r is None:
                if nombre in NO_APLICA_SI_AUSENTE:
                    salida[i["item_id"]] = ("no_aplica", "La condición no se presenta en este trámite")
            elif r["estado"] in mapa:
                salida[i["item_id"]] = (mapa[r["estado"]], r["detalle"])
    return salida


def items(tramite_id: int) -> list[dict]:
    return db.consultar("SELECT * FROM chequeo_items WHERE tramite_id=? ORDER BY orden", (tramite_id,))


def marcar(item_pk: int, estado: str, observacion: str, usuario: str) -> None:
    if estado not in ESTADOS:
        raise ValueError(f"Estado no válido: {estado}")
    antes = db.consultar("SELECT * FROM chequeo_items WHERE id=?", (item_pk,))[0]
    if estado == "no_cumple" and not (observacion or "").strip():
        raise ValueError("Escriba la observación de por qué no cumple (irá al acta de observaciones).")
    if antes["estado"] == estado and (antes["observacion"] or "") == (observacion or ""):
        return
    db.ejecutar("UPDATE chequeo_items SET estado=?, observacion=?, revisor=?, fecha=datetime('now','localtime') "
                "WHERE id=?", (estado, observacion, usuario, item_pk))
    auditoria.registrar(usuario, "editar", "chequeo", item_pk,
                        antes={"tramite_id": antes["tramite_id"], "item": antes["item_id"], "estado": antes["estado"],
                               "observacion": antes["observacion"]},
                        despues={"estado": estado, "observacion": observacion})


def aplicar_sugerencias(tramite_id: int, usuario: str, solo_pendientes: bool = True) -> int:
    sug = sugerencias(tramite_id)
    n = 0
    for it in items(tramite_id):
        if it["item_id"] in sug and (it["estado"] == "pendiente" or not solo_pendientes):
            estado, motivo = sug[it["item_id"]]
            obs = it["observacion"] or f"Sugerido por el programa: {motivo}"
            marcar(it["id"], estado, obs, usuario)
            n += 1
    return n


def avance(tramite_id: int) -> dict:
    lista = items(tramite_id)
    total = len(lista)
    c = {e: sum(1 for i in lista if i["estado"] == e) for e in ESTADOS}
    revisados = total - c["pendiente"]
    evaluables = c["cumple"] + c["no_cumple"]
    return {"total": total, **c,
            "avance": revisados / total if total else 0.0,
            "cumplimiento": c["cumple"] / evaluables if evaluables else None,
            "pendientes": [i for i in lista if i["estado"] in ("pendiente", "no_cumple")]}


def observaciones(tramite_id: int) -> list[dict]:
    """Ítems 'no cumple' con su observación: insumo del acta de observaciones."""
    return [i for i in items(tramite_id) if i["estado"] == "no_cumple"]


def exportar_excel(tramite_id: int, ruta) -> str:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    tr = E.tramite(tramite_id)
    exp = E.obtener(tr["expediente_id"])
    secciones = P.valor("listas.secciones")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Lista de chequeo"
    ws.append([f"Lista de chequeo — {E.tipos()[tr['tipo']]['nombre']}"])
    ws.append([f"Radicado {exp['radicado']} · {exp['solicitante']} · trámite #{tr['id']}"])
    a = avance(tramite_id)
    ws.append([f"Avance {a['avance']:.0%} · cumple {a['cumple']} · no cumple {a['no_cumple']} · "
               f"no aplica {a['no_aplica']} · pendientes {a['pendiente']}"])
    ws.append([])
    ws.append(["Sección", "Ítem", "Estado", "Observación", "Fuente", "Revisor", "Fecha"])
    for c in ws[5]:
        c.font = Font(bold=True)
    colores = {"cumple": "E5F4E4", "no_cumple": "FBEBEB", "no_aplica": "F0EFEC", "pendiente": "F9EEDA"}
    for i in items(tramite_id):
        ws.append([secciones.get(i["seccion"], {}).get("nombre", i["seccion"]), i["texto"], ETIQUETAS[i["estado"]],
                   i["observacion"] or "", i["fuente"] or "", i["revisor"] or "", i["fecha"] or ""])
        ws.cell(ws.max_row, 3).fill = PatternFill("solid", fgColor=colores[i["estado"]])
    for col, w in zip("ABCDEFG", (28, 60, 12, 45, 35, 14, 18)):
        ws.column_dimensions[col].width = w
    for fila in ws.iter_rows(min_row=6):
        for c in fila:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws["A1"].font = Font(bold=True, size=13)
    wb.save(ruta)
    return str(ruta)


# ------------------------------------------------ documento al lado del ítem
def subir_documento_item(item_pk: int, origen, usuario: str, fecha_expedicion: str | None = None,
                         nombre_original: str | None = None, tipo_documento: str | None = None) -> dict:
    """Sube el documento de un ítem 'Documento: …' al expediente y marca el ítem.

    Queda 'cumple' si el documento está vigente; si su fecha de expedición supera
    la vigencia, queda 'no cumple' con la observación."""
    it = db.consultar("SELECT * FROM chequeo_items WHERE id=?", (item_pk,))[0]
    if not it["item_id"].startswith("doc:"):
        raise ValueError("Este ítem no es un documento.")
    opciones = it["item_id"][4:].split("|")
    tipo = tipo_documento or opciones[0]
    if tipo not in opciones:
        raise ValueError(f"El tipo {tipo} no corresponde a este ítem ({', '.join(opciones)}).")
    tr = E.tramite(it["tramite_id"])
    r = D.subir(origen, tr["expediente_id"], tr["id"], tipo, usuario, fecha_expedicion, nombre_original=nombre_original)
    vig = D.catalogo()[tipo].get("vigencia_dias")
    estado, obs = "cumple", f"Documento cargado: {nombre_original or r['ruta']}"
    if vig and fecha_expedicion:
        from datetime import date
        edad = (date.fromisoformat(tr["fecha_radicacion"][:10]) - date.fromisoformat(fecha_expedicion[:10])).days
        if edad > vig or edad < 0:
            estado, obs = "no_cumple", f"Documento cargado pero no vigente: expedido {edad} días antes de la radicación (máx. {vig})."
    elif vig and not fecha_expedicion:
        estado, obs = "pendiente", "Documento cargado; falta la fecha de expedición para verificar la vigencia."
    marcar(item_pk, estado, obs, usuario)
    return {**r, "estado": estado}


# --------------------------------------------------- paquete completo
def documentos_pendientes(tramite_id: int) -> list[dict]:
    """Ítems de documentos obligatorios que no están en 'cumple' ni 'no aplica'."""
    generar(tramite_id)
    tr = E.tramite(tramite_id)
    exp = E.obtener(tr["expediente_id"])
    opcionales = {f"doc:{r['tipo']}" for r in D.requisitos(exp, tr) if r["opcional"]}
    return [i for i in items(tramite_id) if i["seccion"] == "documentos" and i["item_id"] not in opcionales
            and i["estado"] not in ("cumple", "no_aplica")]


def paquete(tramite_id: int) -> dict:
    f = db.consultar("SELECT * FROM chequeo_paquete WHERE tramite_id=?", (tramite_id,))
    base = f[0] if f else {"tramite_id": tramite_id, "completo": 0, "fecha_completo": None, "observacion": None,
                           "usuario": None, "fecha": None}
    return {**base, "completo": bool(base["completo"]), "pendientes": documentos_pendientes(tramite_id)}


def marcar_paquete(tramite_id: int, completo: bool, usuario: str, fecha_completo: str | None = None,
                   observacion: str = "", forzar: bool = False, pasar_a_revision: bool = True) -> dict:
    """Marca el paquete documental como completo (o lo reabre).

    No deja marcarlo completo con documentos obligatorios pendientes, salvo
    forzar=True con observación. Si el trámite estaba 'radicado', pasa a
    'en_revision'."""
    from datetime import date
    antes = paquete(tramite_id)
    if completo and antes["pendientes"] and not forzar:
        raise ValueError("Faltan documentos obligatorios: " + "; ".join(i["texto"] for i in antes["pendientes"]))
    if completo and forzar and antes["pendientes"] and not observacion.strip():
        raise ValueError("Para marcar completo con documentos pendientes escriba la observación.")
    fecha_completo = (fecha_completo or date.today().isoformat()) if completo else None
    db.ejecutar("INSERT INTO chequeo_paquete (tramite_id, completo, fecha_completo, observacion, usuario, fecha) "
                "VALUES (?,?,?,?,?,datetime('now','localtime')) ON CONFLICT(tramite_id) DO UPDATE SET "
                "completo=excluded.completo, fecha_completo=excluded.fecha_completo, observacion=excluded.observacion, "
                "usuario=excluded.usuario, fecha=excluded.fecha",
                (tramite_id, int(completo), fecha_completo, observacion, usuario))
    auditoria.registrar(usuario, "editar", "paquete", tramite_id,
                        antes={"completo": antes["completo"], "fecha_completo": antes["fecha_completo"]},
                        despues={"completo": completo, "fecha_completo": fecha_completo, "observacion": observacion,
                                 "pendientes": len(antes["pendientes"])})
    tr = E.tramite(tramite_id)
    if completo and pasar_a_revision and tr["estado"] == "radicado":
        E.editar_tramite(tramite_id, {"estado": "en_revision"}, usuario, "Paquete documental completo para revisión")
    return paquete(tramite_id)
