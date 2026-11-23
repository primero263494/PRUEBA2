"""Pruebas del módulo 6 (calculadoras)."""
import math
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import ajustes  # noqa: E402

_tmpdir = Path(tempfile.mkdtemp())
ajustes.ruta_bd = lambda: _tmpdir / "prueba6.db"

from core import calc_cientifica as CC, calculadoras as K, db, expedientes as E  # noqa: E402

db.migrar()
E.migrar()
K.migrar()


def test_cientifica():
    assert CC.evaluar("2,5*120 + raiz(81)") == 309.0
    assert CC.evaluar("15%*200") == 30.0
    assert math.isclose(CC.evaluar("sen(30)"), 0.5)
    assert math.isclose(CC.evaluar("sin(pi/6)", grados=False), 0.5)
    assert CC.evaluar("3^4") == 81
    assert CC.evaluar("ans*2", ans=21) == 42
    assert CC.evaluar("m+1", memoria=9) == 10
    assert CC.evaluar("fact(5)") == 120
    assert math.isclose(CC.evaluar("log(1000)"), 3)
    for malo in ("__import__('os')", "1/0", "open('x')", "2**99999", "a+b"):
        try:
            CC.evaluar(malo)
            assert False, malo
        except ValueError:
            pass


def test_indices_contra_ficha_y_planos():
    r = K.indices(200, 160, [160, 160, 160], 0, "S1-CN-1", io_planos=0.80, ic_planos=2.5)
    res = r["resultado"]
    assert res["io"] == 0.8 and res["ic"] == 2.4 and res["cumple_io"] and res["cumple_ic"]
    assert res["dif_io_planos"] == 0.0 and res["dif_ic_planos"] == -0.1
    estados = {p["concepto"]: p["estado"] for p in r["pasos"]}
    assert estados["Diferencia IC con planos"] == "REVISAR"
    r2 = K.indices(100, 95, [95, 95, 95], 0, "S1-CN-1")
    assert not r2["resultado"]["cumple_io"] and not r2["resultado"]["cumple_ic"]


def test_cuadro_areas_e_inconsistencias():
    pisos = [{"piso": "1", "uso": "residencial", "privada": 300, "comun": 40},
             {"piso": "2", "uso": "residencial", "privada": 320, "comun": 20},
             {"piso": "1", "uso": "comercio", "privada": 60, "comun": 0}]
    c = K.cuadro_areas(5000, 400, 0, 600, 650, 40, 60, pisos=pisos,
                       declarado={"area_neta": 4000, "area_util": 2600, "area_construida": 700})
    filas = {f["concepto"]: f["m2"] for f in c["filas"]}
    assert filas["Área neta urbanizable"] == 4000 and filas["Área útil"] == 2550
    assert c["por_piso"] == {"1": 400, "2": 340} and c["por_uso"]["comercio"] == 60
    assert c["total_construida"] == 740 and c["privada"] == 680 and c["comun"] == 60
    textos = " ".join(c["inconsistencias"])
    assert "Area util" in textos and "Area construida" in textos and "Area neta" not in textos
    x = K.cuadro_a_excel(c, _tmpdir / "c.xlsx")
    w = K.cuadro_a_word(c, _tmpdir / "c.docx")
    assert Path(x).stat().st_size > 0 and Path(w).stat().st_size > 0


def test_plusvalia_cambio_uso_y_mayor_aprovechamiento():
    r = K.plusvalia("cambio_o_modificacion_de_uso", 1000, 100, 50, precio_antes=500_000, precio_despues=800_000)
    assert r["area_objeto"] == 850 and r["efecto_m2"] == 300_000
    assert r["efecto_total"] == 255_000_000 and r["participacion"] == 102_000_000      # 40 %
    r30 = K.plusvalia("cambio_o_modificacion_de_uso", 1000, 100, 50, precio_antes=500_000, precio_despues=800_000,
                      tasa_id="0.30", forma_pago="obras_o_suelo")
    assert r30["participacion"] == round(255_000_000 * 0.30 * 0.95)
    m = K.plusvalia("mayor_aprovechamiento_edificabilidad", 1000, precio_referencia=2_000_000, m2_adicionales=500)
    assert m["efecto_total"] == 1_000_000_000 and m["efecto_m2"] == 1_000_000 and m["participacion"] == 400_000_000
    try:
        K.plusvalia("mayor_aprovechamiento_edificabilidad", 1000)
        assert False
    except ValueError:
        pass


def test_liquidacion():
    r = K.liquidar_delineacion([{"uso": "residencial_urbano_e2", "m2": 100, "regla": "obra_nueva"},
                                {"uso": "comercial_urbano", "m2": 50, "regla": "reforma_sin_subdivision"}])
    assert r["total"] == 100 * 35000 + 50 * 87000 * 0.25
    u = K.liquidar_expensa("urbanizacion", area_neta=1000)
    assert u["total"] == round(0.10 * 58363.50 * 1000)
    s = K.liquidar_expensa("subdivision", unidades=3)
    assert s["total"] == 3 * 1750905


def test_guardar_en_tramite():
    eid = E.crear({"solicitante": "x"}, "f")
    tid = E.agregar_tramite(eid, "construccion_urbana", "obra_nueva", {}, "f")
    r = K.indices(200, 160, [160], 0, "S1-CN-1")
    K.guardar(tid, "indices", {"lote": 200}, r, "f")
    assert K.listar(tid)[0]["resultado"]["resultado"]["io"] == 0.8


if __name__ == "__main__":
    import inspect
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_") and inspect.isfunction(f):
            f()
            print("ok", nombre)
