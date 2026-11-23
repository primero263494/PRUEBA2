"""Pruebas del módulo 5 (listas de chequeo)."""
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import ajustes  # noqa: E402

_tmpdir = Path(tempfile.mkdtemp())
ajustes.ruta_bd = lambda: _tmpdir / "prueba5.db"

from core import documentos as D  # noqa: E402

D.EXPEDIENTES_DIR = _tmpdir / "expedientes"
D.PAPELERA = _tmpdir / "papelera"

from core import auditoria, chequeo as C, db, expedientes as E  # noqa: E402

db.migrar()
E.migrar()
D.migrar()
C.migrar()
HOY = date.today()


def _tramite(tipo="construccion_urbana", **datos):
    eid = E.crear(dict(solicitante="Prueba", matricula="020-1", cedula_catastral="1" * 30, direccion="x",
                       clase_suelo="urbano", poligono="S1-CN-1", area_actividad="residencial"), "f")
    return E.agregar_tramite(eid, tipo, "obra_nueva", datos, "f")


def test_generar_por_tipo_y_sin_duplicar():
    tid = _tramite()
    n = C.generar(tid)
    secciones = {i["seccion"] for i in C.items(tid)}
    assert {"viabilidad", "normativa", "arquitectura", "estructura", "documentos"} <= secciones
    assert "urbanismo" not in secciones
    assert any(i["item_id"] == "doc:fun" for i in C.items(tid))
    assert not any(i["item_id"] == "t_reconocimiento" for i in C.items(tid))   # solo para reconocimiento
    assert C.generar(tid) == 0 and len(C.items(tid)) == n


def test_prorroga_lista_corta():
    tid = _tramite("prorroga")
    C.generar(tid)
    secciones = {i["seccion"] for i in C.items(tid)}
    assert secciones == {"documentos", "tramite_especial"}
    assert any(i["item_id"] == "t_prorroga" for i in C.items(tid))


def test_marcar_y_avance():
    tid = _tramite()
    C.generar(tid)
    lista = C.items(tid)
    C.marcar(lista[0]["id"], "cumple", "", "revisor1")
    C.marcar(lista[1]["id"], "no_aplica", "", "revisor1")
    try:
        C.marcar(lista[2]["id"], "no_cumple", "", "revisor1")
        assert False, "no cumple exige observación"
    except ValueError:
        pass
    C.marcar(lista[2]["id"], "no_cumple", "Falta plan de manejo de suelos", "revisor1")
    a = C.avance(tid)
    assert a["cumple"] == 1 and a["no_aplica"] == 1 and a["no_cumple"] == 1
    assert round(a["avance"], 4) == round(3 / a["total"], 4)
    assert a["cumplimiento"] == 0.5
    assert C.observaciones(tid)[0]["observacion"] == "Falta plan de manejo de suelos"
    assert any(x["entidad"] == "chequeo" for x in auditoria.listar())


def test_sugerencias_desde_verificacion_y_documentos():
    tid = _tramite(area_lote=200, area_ocupada_piso1=190, area_construida=400, n_pisos=3,
                   uso_principal="residencial", n_viviendas=1)
    tr = E.tramite(tid)
    p = _tmpdir / "FUN.pdf"
    p.write_bytes(b"x")
    D.subir(p, tr["expediente_id"], tid, None, "f")
    C.generar(tid)
    sug = C.sugerencias(tid)
    assert sug["doc:fun"][0] == "cumple"
    assert sug["n_io"][0] == "no_cumple"            # 95 % > 85 %
    assert sug["n_ic"][0] == "cumple"               # 2,0 ≤ 2,5
    assert sug["v_plan_parcial"][0] == "no_aplica"
    assert "e_suelos" not in sug                    # 3 pisos: no se sugiere nada
    n = C.aplicar_sugerencias(tid, "revisor1")
    assert n == len(sug)
    io = next(i for i in C.items(tid) if i["item_id"] == "n_io")
    assert io["estado"] == "no_cumple" and "IO" in io["observacion"]


def test_exportar_excel():
    tid = _tramite()
    C.generar(tid)
    ruta = C.exportar_excel(tid, _tmpdir / "lista.xlsx")
    import openpyxl
    ws = openpyxl.load_workbook(ruta).active
    assert ws["A5"].value == "Sección" and ws.max_row > 20


if __name__ == "__main__":
    import inspect
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_") and inspect.isfunction(f):
            f()
            print("ok", nombre)
