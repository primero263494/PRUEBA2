"""Pruebas del módulo 2 (expedientes, trámites y verificación)."""
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import ajustes  # noqa: E402

_tmp = Path(tempfile.mkdtemp()) / "prueba2.db"
RUTA_BD = lambda: _tmp
ajustes.ruta_bd = RUTA_BD

from core import auditoria, calendario, db, documentos, expedientes as E, verificacion as V  # noqa: E402
from core import parametros as P  # noqa: E402

db.migrar()
E.migrar()
documentos.migrar()

HOY = date.today()


def _exp(**kw):
    base = dict(solicitante="Ana Gómez", matricula="020-12345", cedula_catastral="0" * 30,
                direccion="Cra 30 # 31-20", clase_suelo="urbano", poligono="S1-CN-1",
                area_actividad="residencial", fecha_radicacion=HOY.isoformat())
    base.update(kw)
    return E.obtener(E.crear(base, "funcionario1"))


def _estado(res, item):
    return next(r["estado"] for r in res if r["item"] == item)


def test_festivos_y_dias_habiles():
    f = calendario.festivos(2026)
    assert date(2026, 4, 2) in f and date(2026, 4, 3) in f      # jueves y viernes santo 2026
    assert date(2026, 1, 12) in f                                # Reyes trasladado al lunes
    assert date(2026, 12, 25) in f
    assert calendario.sumar_dias_habiles(date(2026, 12, 23), 2) == date(2026, 12, 28)


def test_radicado_consecutivo():
    r1 = _exp()["radicado"]
    r2 = _exp()["radicado"]
    aa = f"{HOY.year % 100:02d}"
    assert r1 == f"05148-0-{aa}-0001" and r2 == f"05148-0-{aa}-0002"


def test_verificacion_cumple():
    e = _exp()
    tid = E.agregar_tramite(e["id"], "construccion_urbana", "obra_nueva", {
        "area_lote": 200, "area_ocupada_piso1": 160, "area_construida": 480, "n_pisos": 3,
        "uso_principal": "residencial", "n_viviendas": 3, "frente_lote": 8,
        "fecha_cert_tradicion": (HOY - timedelta(days=10)).isoformat(),
        "fecha_paz_salvo": (HOY - timedelta(days=5)).isoformat()}, "funcionario1")
    res = V.verificar(e, E.tramite(tid))
    assert _estado(res, "Campos obligatorios") == V.CUMPLE
    assert _estado(res, "Índice de ocupación") == V.CUMPLE           # 80 % ≤ 85 %
    assert _estado(res, "Índice de construcción") == V.CUMPLE        # 2,4 ≤ 2,5
    assert _estado(res, "Altura") == V.CUMPLE
    assert _estado(res, "Uso permitido") == V.CUMPLE
    assert _estado(res, "Certificado de tradición") == V.CUMPLE
    assert E.tramite(tid)["fecha_limite"] == calendario.sumar_dias_habiles(HOY, 45).isoformat()


def test_verificacion_incumple_y_ic_especial():
    e = _exp()
    tid = E.agregar_tramite(e["id"], "construccion_urbana", "obra_nueva", {
        "area_lote": 100, "area_ocupada_piso1": 95, "area_construida": 350, "n_pisos": 9,
        "uso_principal": "1011", "n_viviendas": 4, "frente_lote": 6, "seccion_via": 7,
        "fecha_cert_tradicion": (HOY - timedelta(days=60)).isoformat()}, "funcionario1")
    res = V.verificar(e, E.tramite(tid))
    assert _estado(res, "Índice de ocupación") == V.NO_CUMPLE        # 95 %
    assert _estado(res, "Índice de construcción") == V.NO_CUMPLE     # 3,5 con opción 2,5
    assert _estado(res, "Altura") == V.NO_CUMPLE                     # 9 > 5 + 3
    assert _estado(res, "Uso permitido") == V.NO_CUMPLE              # 1011 prohibido en residencial
    assert _estado(res, "Certificado de tradición") == V.NO_CUMPLE
    assert _estado(res, "Altura por sección vial") == V.NO_CUMPLE
    assert _estado(res, "Lote mínimo multifamiliar") == V.NO_CUMPLE
    from core import auth
    auth.crear_usuario("admin", "Admin", "administrador", "clave-segura-1", "sistema")
    P.modificar("pbot.indice_construccion_maximo", "4.0", "admin", "Prueba autorización especial")
    assert _estado(V.verificar(e, E.tramite(tid)), "Índice de construcción") == V.REVISAR
    P.restaurar("pbot.indice_construccion_maximo", "admin", "fin prueba")


def test_altura_adicional_revisar():
    e = _exp()
    tid = E.agregar_tramite(e["id"], "construccion_urbana", "obra_nueva",
                            {"area_lote": 300, "n_pisos": 7}, "funcionario1")
    assert _estado(V.verificar(e, E.tramite(tid)), "Altura") == V.REVISAR   # 5 base + 3 adicional


def test_reconocimiento_y_prorroga():
    e = _exp()
    t1 = E.agregar_tramite(e["id"], "reconocimiento", "urbano",
                           {"area_lote": 120, "area_construida": 200, "n_pisos": 2, "fecha_conclusion_obra": "2015-03-01"}, "f")
    assert _estado(V.verificar(e, E.tramite(t1)), "Antigüedad de la edificación") == V.NO_CUMPLE
    t2 = E.agregar_tramite(e["id"], "prorroga", "prorroga",
                           {"licencia_anterior": "L-1", "fecha_vencimiento_licencia": (HOY + timedelta(days=20)).isoformat()}, "f")
    assert _estado(V.verificar(e, E.tramite(t2)), "Oportunidad de la prórroga") == V.CUMPLE


def test_expansion_y_rural():
    e = _exp(clase_suelo="expansion", poligono="S3-DE-8")
    t = E.agregar_tramite(e["id"], "urbanizacion", "desarrollo", {"area_lote": 15000, "n_viviendas": 150}, "f")
    res = V.verificar(e, E.tramite(t))
    assert _estado(res, "Plan parcial") == V.REVISAR
    assert _estado(res, "Arqueología preventiva") == V.REVISAR
    assert _estado(res, "Densidad") == V.CUMPLE                       # 150 ≤ 165
    r = _exp(clase_suelo="rural", poligono="")
    t = E.agregar_tramite(r["id"], "subdivision", "subdivision_rural", {"area_lote": 30000, "n_unidades_resultantes": 5}, "f")
    assert _estado(V.verificar(r, E.tramite(t)), "Número de predios") == V.NO_CUMPLE


def test_eliminar_tramite_deja_copia():
    e = _exp()
    tid = E.agregar_tramite(e["id"], "cerramiento", "cerramiento", {"area_lote": 90}, "f")
    try:
        E.eliminar_tramite(tid, "f", "")
        assert False
    except ValueError:
        pass
    E.eliminar_tramite(tid, "f", "Cargado por error en otro expediente")
    assert E.tramite(tid) is None
    reg = [a for a in auditoria.listar(entidad="tramite") if a["accion"] == "eliminar"]
    assert reg and '"cerramiento"' in reg[0]["antes"]
    assert any(h["accion"] == "eliminar" for h in E.historial(e["id"]))


def test_editar_y_buscar():
    e = _exp(solicitante="Constructora XYZ S.A.S.", tipo_persona="juridica")
    E.editar(e["id"], {"estado": "en_revision"}, "f", "inicio de revisión")
    assert E.obtener(e["id"])["estado"] == "en_revision"
    assert E.listar("XYZ")[0]["id"] == e["id"]
    assert E.listar(estado="en_revision")


if __name__ == "__main__":
    import inspect
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_") and inspect.isfunction(f):
            f()
            print("ok", nombre)
