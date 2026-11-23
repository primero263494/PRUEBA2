"""Pruebas del módulo 1 (consulta normativa)."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import ajustes  # noqa: E402

_tmp = Path(tempfile.mkdtemp()) / "prueba1.db"
ajustes.ruta_bd = lambda: _tmp

from core import cesiones, consulta, db, normas  # noqa: E402

db.migrar()


def test_ficha_poligono_con_fuentes():
    f = consulta.ficha_poligono("S1-CN-1")
    aprov = {i["etiqueta"]: i for i in f["secciones"]["Aprovechamientos"]}
    assert aprov["Índice de construcción (IC)"]["valor"] == "2.5"
    assert aprov["Altura base"]["valor"] == "5 pisos"
    assert all(i["fuente"] for s in f["secciones"].values() for i in s)
    assert "133" in consulta.ficha_poligono("S3-DE-8")["secciones"]["Condición del tratamiento"][0]["fuente"]
    assert consulta.ficha_poligono("NO-EXISTE") is None


def test_usos():
    assert len(consulta.tabla_usos()) == 326
    r = consulta.buscar_usos("1011")[0]
    assert (r["uso_social_obligado"], r["residencial"], r["comercio_servicios"], r["artesanal"]) == ("R", "PH", "PH", "P")
    panaderia = consulta.buscar_usos("panaderia")
    assert panaderia, "debe encontrar sin tildes"
    prohibidos_res = consulta.buscar_usos("", "residencial", {"PH"})
    assert all(x["residencial"] == "PH" for x in prohibidos_res)


def test_cesiones_ejemplo():
    r = cesiones.urbanas(**cesiones.EJEMPLO_URBANO)
    assert r["area_neta"] == 4000.0                       # 5000 − 400 − 600
    assert r["tipo_b_o_ep"] == 800.0                      # 20 % × 4000
    assert r["tipo_c_construida"] == 40 * 1.5 + 200 * 0.015
    assert r["multifamiliar"] == 4200 * 0.02
    assert r["area_util"] == 4000 - 650 - 800
    assert all(p["fuente"] for p in r["pasos"])


def test_cesiones_vis_y_parcelacion():
    r = cesiones.urbanas(1000, vis_vip=True)
    assert r["tipo_b_o_ep"] == 150.0 and r["tipo_c_suelo"] == 50.0
    p = cesiones.parcelacion(20000, 6, True)
    resultados = [x["resultado"] for x in p["pasos"]]
    assert 4000.0 in resultados and 400.0 in resultados and 30 in resultados


def test_compensacion_pide_valor():
    assert cesiones.compensacion(100, None, "B")["valor"] is None
    assert cesiones.compensacion(100, 500000, "B")["valor"] == 50_000_000


def test_buscador_y_normas_base():
    cargadas = normas.cargar_base("prueba")
    assert {c["nombre"] for c in cargadas} >= {"Ley 388 de 1997", "Acuerdo 012 de 2017 (PBOT)"}
    r = consulta.buscar("plusvalía")
    assert r["parametros"] and r["articulos"]
    assert consulta.buscar("S3-DU-7")["poligonos"]
    assert normas.cargar_base("prueba") == []            # no repite
    for n in normas.listar():
        normas.eliminar(n["id"], "prueba", "limpieza de prueba")


if __name__ == "__main__":
    import inspect
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_") and inspect.isfunction(f):
            f()
            print("ok", nombre)
