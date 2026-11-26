"""Lógica de la pantalla de inicio por tareas y perfiles (propuesta C).

Todo lo que la pantalla muestra se calcula aquí, sin Streamlit, para poder
probarlo: las tareas que ve cada perfil, los pendientes del funcionario con su
siguiente paso, los avisos del sistema y el buscador único.
"""
from __future__ import annotations

import re
from datetime import date

from core import calendario, cartografia, chequeo, consulta, db, expedientes as E, informes, normas
from core import parametros as P
from core.planos import analisis as A

CERRADOS = ("licencia_expedida", "negado", "desistido", "archivado")

# (clave, título, descripción, página de destino, permiso, perfiles que la ven)
TAREAS = [
    ("radicar", "Radicar un trámite", "Solicitante, predio, tipo y requisitos", "Expedientes y trámites",
     "expedientes", ("funcionario", "administrador")),
    ("documentos", "Revisar documentos", "Lista de chequeo y paquete completo", "Listas de chequeo",
     "expedientes", ("funcionario", "administrador")),
    ("planos", "Analizar planos", "Arquitectura, estructura, suelos y cruce", "Análisis de planos",
     "analizar_planos", ("funcionario", "administrador")),
    ("calcular", "Calcular", "IO/IC, cuadro de áreas, cesiones, plusvalía, tarifas", "Calculadoras",
     "ver_norma", ("consulta", "funcionario", "administrador")),
    ("informe", "Generar informe o acta", "Word y PDF con la plantilla", "Informes",
     "informes", ("funcionario", "administrador")),
    ("norma", "Consultar la norma", "Ficha del predio, usos y requisitos por trámite", "Consulta normativa",
     "ver_norma", ("consulta", "funcionario", "administrador")),
    ("cartografia", "Ver cartografía", "Capas del PBOT y cruce del predio", "Cartografía",
     "ver_cartografia", ("consulta",)),
    ("parametros", "Parámetros normativos", "Valores con su norma; cambios con motivo", "Parámetros normativos",
     "*", ("administrador",)),
    ("configuracion", "Configuración", "Plantilla de informes, lectura de escaneos, DWG", "Configuración",
     "*", ("administrador",)),
    ("usuarios", "Usuarios y auditoría", "Cuentas, perfiles y registro de cambios", "Usuarios",
     "*", ("administrador",)),
]
PERFILES = {"consulta": "Consulta", "funcionario": "Funcionario", "administrador": "Administrador"}
ORDEN_PERFIL = ["consulta", "funcionario", "administrador"]


def perfiles_visibles(rol: str) -> list[str]:
    """Un usuario puede ver la pantalla de su perfil y la de los perfiles inferiores."""
    return ORDEN_PERFIL[: ORDEN_PERFIL.index(rol) + 1] if rol in ORDEN_PERFIL else ["consulta"]


def tareas(perfil: str, rol: str) -> list[dict]:
    from core import auth
    claves = ("clave", "titulo", "sub", "pagina", "permiso", "perfiles")
    return [dict(zip(claves, t)) for t in TAREAS if perfil in t[5] and auth.puede(rol, t[4])]


# ------------------------------------------------------------------ pendientes
def _dias_restantes(fecha_limite: str | None) -> int | None:
    if not fecha_limite:
        return None
    hoy, fin = date.today(), date.fromisoformat(fecha_limite[:10])
    if fin >= hoy:
        return calendario.dias_habiles_entre(hoy, fin)
    return -calendario.dias_habiles_entre(fin, hoy)


def siguiente_paso(tramite: dict) -> dict:
    """Qué toca hacer ahora con el trámite y en qué página: {texto, accion, pagina}."""
    tid = tramite["id"]
    estado = tramite["estado"]
    if estado == "acta_observaciones":
        return {"texto": "Esperando respuesta al acta de observaciones", "accion": "Ver acta", "pagina": "Informes"}
    if estado == "en_correcciones":
        return {"texto": "Llegaron correcciones: revisar documentos y planos", "accion": "Revisar", "pagina": "Listas de chequeo"}
    pq = chequeo.paquete(tid)
    if not pq["completo"]:
        n = len(pq["pendientes"])
        if n:
            return {"texto": f"Faltan {n} documento{'s' if n > 1 else ''} del paquete", "accion": "Continuar",
                    "pagina": "Listas de chequeo"}
        return {"texto": "Documentos completos: marcar el paquete", "accion": "Marcar paquete", "pagina": "Listas de chequeo"}
    tipo = E.tipos()[tramite["tipo"]]
    con_planos = any(v in tipo.get("verificaciones", []) for v in ("indices", "altura", "estudio_suelos"))
    an = A.ultimo(tid)
    if con_planos and not an:
        return {"texto": "Paquete completo: analizar planos y estudios", "accion": "Analizar", "pagina": "Análisis de planos"}
    if an and an["concepto"]["conteo"].get("NO CUMPLE"):
        n = an["concepto"]["conteo"]["NO CUMPLE"]
        return {"texto": f"Análisis de planos con {n} NO CUMPLE: generar acta", "accion": "Generar acta", "pagina": "Informes"}
    av = chequeo.avance(tid)
    if av["pendiente"]:
        return {"texto": f"Lista de chequeo: {av['pendiente']} ítems por revisar", "accion": "Revisar", "pagina": "Listas de chequeo"}
    if not informes.listar(tid):
        return {"texto": "Revisión completa: generar informe técnico", "accion": "Generar informe", "pagina": "Informes"}
    return {"texto": "Informe generado: liquidar y expedir", "accion": "Liquidar", "pagina": "Calculadoras"}


def pendientes(usuario: dict | None = None, solo_mios: bool = False, limite: int = 12) -> list[dict]:
    """Trámites abiertos ordenados por vencimiento, con su siguiente paso.

    'Míos' = expedientes cuyo responsable es el usuario (por usuario o nombre)."""
    sql = ("SELECT t.*, e.radicado, e.solicitante, e.responsable FROM tramites t JOIN expedientes e ON e.id=t.expediente_id "
           f"WHERE t.estado NOT IN ({','.join('?' * len(CERRADOS))}) ORDER BY t.fecha_limite IS NULL, t.fecha_limite")
    filas = db.consultar(sql, CERRADOS)
    if solo_mios and usuario:
        quien = {str(usuario.get("usuario", "")).lower(), str(usuario.get("nombre", "")).lower()} - {""}
        filas = [f for f in filas if str(f.get("responsable") or "").lower() in quien]
    salida = []
    for f in filas[:limite]:
        dias = _dias_restantes(f["fecha_limite"])
        if dias is None:
            plazo, nivel = "Sin término", "normal"
        elif dias < 0:
            plazo, nivel = f"Vencido hace {-dias} días hábiles", "vencido"
        elif dias <= 5:
            plazo, nivel = f"Vence en {dias} días hábiles", "urgente"
        elif dias <= 10:
            plazo, nivel = f"Vence en {dias} días hábiles", "pronto"
        else:
            plazo, nivel = f"{dias} días hábiles", "normal"
        salida.append({"tramite_id": f["id"], "expediente_id": f["expediente_id"], "radicado": f["radicado"],
                       "solicitante": f["solicitante"], "tipo": E.tipos()[f["tipo"]]["nombre"], "estado": f["estado"],
                       "fecha_limite": f["fecha_limite"], "dias": dias, "plazo": plazo, "nivel": nivel,
                       "paso": siguiente_paso(f)})
    return salida


# --------------------------------------------------------------------- avisos
def avisos() -> list[dict]:
    """Lo que falta configurar o cargar: [{texto, pagina}]."""
    from core import respaldo
    salida = []
    if respaldo.en_la_nube():
        u = respaldo.ultimo()
        salida.append({"texto": "Está en Streamlit Cloud: los datos se borran cuando el servidor se reinicia. "
                                "Descargue un respaldo al terminar cada jornada" +
                                (f" (último: {u})." if u else " (aún no hay ninguno)."), "pagina": "Configuración"})
    pend = P.pendientes()
    if pend:
        salida.append({"texto": f"{len(pend)} parámetros normativos pendientes de dato.", "pagina": "Parámetros normativos"})
    faltan = cartografia.roles_faltantes()
    if faltan:
        nombres = ", ".join(cartografia.ROLES[r][0].lower() for r in faltan[:4]) + ("…" if len(faltan) > 4 else "")
        salida.append({"texto": f"Cartografía sin cargar: {nombres}.", "pagina": "Cartografía"})
    pl = informes.plantilla()
    if not pl.get("logo") or any("[" in str(pl.get(k, "")) for k in ("direccion", "telefono", "correo")) or \
            any("[" in str(f.get("nombre", "")) for f in pl.get("firmas", [])):
        salida.append({"texto": "Plantilla de informes sin logo, dirección o firmas.", "pagina": "Configuración"})
    if not normas.listar():
        salida.append({"texto": "No hay textos de norma cargados para buscar artículos.", "pagina": "Normas cargadas"})
    return salida


# ------------------------------------------------------------------ buscador
RE_RADICADO = re.compile(r"^\d{5}-\d-\d{2}-\d{1,4}$")
RE_POLIGONO = re.compile(r"^S\d-[A-Z]{1,2}-\d{1,2}$", re.I)


def buscar(texto: str) -> dict:
    """Buscador único: expedientes (radicado, matrícula, cédula catastral, dirección, solicitante),
    polígono del PBOT o pregunta normativa."""
    t = (texto or "").strip()
    if not t:
        return {"tipo": "vacio"}
    exps = E.listar(t)[:10]
    if RE_POLIGONO.match(t):
        ficha = consulta.ficha_poligono(t.upper())
        if ficha:
            return {"tipo": "poligono", "codigo": t.upper(), "ficha": ficha, "expedientes": exps}
    if exps and (RE_RADICADO.match(t) or len(exps) <= 10):
        if RE_RADICADO.match(t) or not _parece_pregunta(t):
            return {"tipo": "expedientes", "expedientes": exps}
    r = consulta.buscar(t)
    return {"tipo": "norma", "resultado": r, "expedientes": exps}


def _parece_pregunta(t: str) -> bool:
    return "?" in t or "¿" in t or len(t.split()) >= 4
