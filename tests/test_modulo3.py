"""Pruebas del módulo 3 (gestión documental). Usan carpetas temporales."""
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import ajustes  # noqa: E402

_tmpdir = Path(tempfile.mkdtemp())
RUTA_BD = lambda: _tmpdir / "prueba3.db"
ajustes.ruta_bd = RUTA_BD

from core import documentos as D  # noqa: E402

D.EXPEDIENTES_DIR = _tmpdir / "expedientes"          # no tocar la carpeta real
D.PAPELERA = _tmpdir / "papelera"
D.PAPELERA.mkdir()

from core import auditoria, db, expedientes as E, verificacion as V, vista_previa  # noqa: E402

db.migrar()
E.migrar()
D.migrar()

HOY = date.today()
PDF = next(Path("/mnt/user-data/uploads").glob("*Decreto_tarifas_2026.pdf"), None)


def _archivo(nombre, contenido=b"contenido de prueba"):
    p = _tmpdir / "origen" / nombre
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(contenido)
    return p


def _exp_tr(tipo="construccion_urbana", **datos):
    eid = E.crear(dict(solicitante="Prueba", matricula="020-1", cedula_catastral="1" * 30, direccion="x",
                       clase_suelo="urbano", poligono="S1-CN-1", area_actividad="residencial"), "f")
    tid = E.agregar_tramite(eid, tipo, None, datos, "f", fecha_radicacion=HOY.isoformat())
    return E.obtener(eid), E.tramite(tid)


def test_sugerir_tipo():
    assert D.sugerir_tipo("Certificado_Tradicion_020-123.pdf") == "cert_tradicion"
    assert D.sugerir_tipo("PAZ Y SALVO predial.pdf") == "paz_salvo"
    assert D.sugerir_tipo("planos estructurales piso 2.dwg") == "planos_estructurales"
    assert D.sugerir_tipo("ESTUDIO DE SUELOS.pdf") == "estudio_suelos"
    assert D.sugerir_tipo("modelo.e2k") == "memorias_calculo"
    assert D.sugerir_tipo("xyz.pdf") == "otro"


def test_subir_versiones_duplicados_y_carpetas():
    exp, tr = _exp_tr()
    r1 = D.subir(_archivo("FUN.pdf"), exp["id"], tr["id"], None, "f")
    assert r1["tipo"] == "fun" and r1["version"] == 1
    assert f"/{exp['radicado']}/{tr['id']}_construccion_urbana/fun/FUN.pdf" in r1["ruta"]
    r2 = D.subir(_archivo("FUN.pdf", b"otra version"), exp["id"], tr["id"], "fun", "f")
    assert r2["version"] == 2 and r2["ruta"].endswith("FUN_v2.pdf")
    r3 = D.subir(_archivo("copia.pdf"), exp["id"], tr["id"], "otro", "f")
    assert r3["duplicado_de"]["nombre_original"] == "FUN.pdf"
    try:
        D.subir(_archivo("virus.exe"), exp["id"], tr["id"], None, "f")
        assert False
    except ValueError:
        pass


def test_faltantes_y_verificacion_usa_fechas_de_documentos():
    exp, tr = _exp_tr(n_pisos=2, area_lote=200)
    f = {x["tipo"]: x["cargado"] for x in D.faltantes(exp, tr)}
    assert "estudio_suelos|apique" in f and not f["fun"]
    D.subir(_archivo("Certificado tradicion.pdf"), exp["id"], tr["id"], None, "f",
            fecha_expedicion=(HOY - timedelta(days=45)).isoformat())
    D.subir(_archivo("apique.pdf"), exp["id"], tr["id"], None, "f")
    f = {x["tipo"]: x["cargado"] for x in D.faltantes(exp, tr)}
    assert f["cert_tradicion"] and f["estudio_suelos|apique"]
    assert D.vencidos(exp, tr)[0]["edad_dias"] == 45
    res = V.verificar(exp, E.tramite(tr["id"]))
    estados = {r["item"]: r["estado"] for r in res}
    assert estados["Certificado de tradición"] == V.NO_CUMPLE
    assert estados["Documentos exigidos"] == V.NO_CUMPLE


def test_juridica_e_icanh():
    eid = E.crear(dict(solicitante="Constructora", tipo_persona="juridica", clase_suelo="expansion"), "f")
    tid = E.agregar_tramite(eid, "urbanizacion", "desarrollo", {"area_lote": 12000}, "f")
    req = D.requeridos(E.obtener(eid), E.tramite(tid))
    assert "camara_comercio" in req and "icanh" in req


def test_editar_mueve_y_eliminar_a_papelera():
    exp, tr = _exp_tr()
    r = D.subir(_archivo("documento.pdf"), exp["id"], tr["id"], "otro", "f")
    D.editar(r["id"], {"tipo_documento": "escritura"}, "f")
    nuevo = D.obtener(r["id"])["archivo"]
    assert "/escritura/" in nuevo and Path(nuevo).exists()
    eliminado = D.eliminar(r["id"], "f", "cargado en el expediente equivocado")
    assert D.obtener(r["id"]) is None and Path(eliminado["papelera"]).exists()
    assert any(a["accion"] == "eliminar" for a in auditoria.listar(entidad="documento"))


def test_eliminar_expediente_mueve_carpeta():
    exp, tr = _exp_tr()
    D.subir(_archivo("fun2.pdf"), exp["id"], tr["id"], "fun", "f")
    E.eliminar_expediente(exp["id"], "admin", "expediente duplicado")
    assert not (D.EXPEDIENTES_DIR / exp["radicado"]).exists()
    assert any(p.name.endswith(exp["radicado"]) for p in D.PAPELERA.iterdir())


def test_vista_previa():
    if PDF:
        v = vista_previa.generar(PDF, "pdf", 1)
        assert v["tipo"] == "imagenes" and v["imagenes"]
    import docx
    import openpyxl
    d = docx.Document()
    d.add_paragraph("Hola norma")
    pd_ = _tmpdir / "x.docx"
    d.save(pd_)
    assert "Hola norma" in vista_previa.generar(pd_, "docx")["texto"]
    wb = openpyxl.Workbook()
    wb.active.append(["area", "valor"])
    wb.active.append(["lote", 200])
    px = _tmpdir / "x.xlsx"
    wb.save(px)
    assert "Sheet" in vista_previa.generar(px, "xlsx")["tablas"]
    assert vista_previa.generar(_archivo("m.e2k", b"$ STORIES"), "e2k")["tipo"] == "texto"
    assert vista_previa.generar(_archivo("a.rvt"), "rvt")["tipo"] == "sin_vista"


if __name__ == "__main__":
    import inspect
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_") and inspect.isfunction(f):
            f()
            print("ok", nombre)
