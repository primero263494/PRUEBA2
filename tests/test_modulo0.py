"""Pruebas del módulo 0. Ejecutar:  python -m pytest tests  (o python tests/test_modulo0.py)

Usan una base de datos temporal; no tocan la real.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import ajustes  # noqa: E402

_tmp = Path(tempfile.mkdtemp()) / "prueba.db"
RUTA_BD = lambda: _tmp
ajustes.ruta_bd = RUTA_BD# base temporal

from core import auditoria, auth, db, normas, sismo  # noqa: E402
from core import parametros as P  # noqa: E402

db.migrar()


def test_parametros_cargan_con_fuente():
    todos = P.todos()
    assert len(todos) > 150
    sin_fuente = [c for c, p in todos.items() if not p.fuente and not c.startswith("nacional.normograma")]
    assert sin_fuente == [], sin_fuente


def test_opciones_tienen_eleccion_valida():
    for c, p in P.todos().items():
        if p.opciones:
            assert p.opcion_elegida() is not None, c


def test_valores_clave():
    assert P.valor("pbot.cesiones_urbanas.tipo_b_porcentaje_area_neta") == 0.20
    assert P.valor("pbot.plusvalia.tasa_participacion") == 0.40
    assert P.valor("pbot.indice_construccion_maximo") == 2.5
    assert P.valor("nsr10.amenaza_sismica_municipio.Aa") == 0.15
    assert P.valor("nsr10.amenaza_sismica_municipio.Av") == 0.20
    assert P.valor("tarifas.bases.uvt") == 52374


def test_poligonos():
    assert len(P.poligonos()) == 59
    p = P.poligono("s1-cn-1")
    assert p["ic"] == "2.5" and p["io_urbanismos"] == "85%"


def test_opcion_ic_4_y_motivo_obligatorio():
    auth.crear_usuario("admin", "Admin", "administrador", "clave-segura-1", "sistema")
    try:
        P.modificar("pbot.indice_construccion_maximo", "4.0", "admin", "")
        assert False, "debía exigir motivo"
    except ValueError:
        pass
    P.modificar("pbot.indice_construccion_maximo", "4.0", "admin", "Resolución de autorización 123")
    assert P.valor("pbot.indice_construccion_maximo") == 4.0
    P.restaurar("pbot.indice_construccion_maximo", "admin", "prueba")
    assert P.valor("pbot.indice_construccion_maximo") == 2.5
    assert any(a["entidad"] == "parametro" for a in auditoria.listar())


def test_tarifas_nota_y_reglas():
    alertas = {p.clave.split(".")[-1] for p in P.alertas_tarifas()}
    assert alertas == {"residencial_urbano_e3", "residencial_urbano_e6", "industrial_bodega_rural_suburbano"}
    t = P.tarifa_m2("residencial_urbano_e3")
    assert t["aplicado"] == 39000 and t["millar_superior"] == 44000
    P.modificar("tarifas.bases.regla_redondeo", "millar_superior", "admin", "Prueba de regla")
    assert P.tarifa_m2("residencial_urbano_e3")["aplicado"] == 44000
    P.modificar("tarifas.delineacion_m2.residencial_urbano_e3", 43000, "admin", "Corrección Hacienda")
    assert P.tarifa_m2("residencial_urbano_e3")["aplicado"] == 43000
    P.restaurar("tarifas.delineacion_m2.residencial_urbano_e3", "admin", "prueba")
    P.restaurar("tarifas.bases.regla_redondeo", "admin", "prueba")
    assert P.tarifa_m2("residencial_urbano_e1")["aplicado"] == 22000


def test_area_neta_tres_opciones():
    p = P.obtener("pbot.definiciones.area_neta")
    assert [o["id"] for o in p.opciones] == ["pbot_art137", "decreto_tarifas_2026", "manual_tramites"]
    assert p.opcion_elegida()["id"] == "pbot_art137"


def test_sismo():
    assert sismo.Fa("D") == 1.5      # interpolado entre 1.6 (0.1) y 1.4 (0.2) para Aa=0.15
    assert sismo.Fv("D") == 2.0      # Av=0.20
    e = sismo.espectro("D", "I")
    assert e["TC"] == round(0.48 * 0.20 * 2.0 / (0.15 * 1.5), 3)
    assert sismo.categoria_unidad(3) == "Baja"
    assert sismo.categoria_unidad(3, 2000) == "Media"
    assert sismo.sondeos_minimos("Media") == {"numero": 4, "profundidad_m": 15}
    assert sismo.separacion_minima(5, 15.0, "losas_no_coinciden") == 0.45
    assert sismo.deriva_maxima() == 0.010


def test_auth():
    assert auth.verificar("admin", "clave-segura-1")["rol"] == "administrador"
    assert auth.verificar("admin", "otra") is None
    assert auth.puede("funcionario", "cargar_norma")
    assert not auth.puede("consulta", "cargar_norma")


def test_normas_carga_y_busqueda():
    txt = Path(tempfile.mkdtemp()) / "norma.txt"
    txt.write_text("ARTÍCULO 1. Objeto. Texto uno.\nARTÍCULO 2. Ochavas. Radio mínimo de 2 m.\n", encoding="utf-8")
    r = normas.cargar(txt, "Norma prueba", "municipal", "urbanistica", "v1", "admin")
    assert r["articulos"] == 2
    assert normas.buscar("ochava")[0]["articulo"] == "2"
    normas.eliminar(r["id"], "admin", "prueba de borrado")
    assert normas.listar() == []


if __name__ == "__main__":
    import inspect
    for nombre, f in list(globals().items()):
        if nombre.startswith("test_") and inspect.isfunction(f):
            f()
            print("ok", nombre)
