"""Pruebas de la pantalla de inicio por tareas y perfiles (propuesta C)."""
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import ajustes  # noqa: E402

_tmpdir = Path(tempfile.mkdtemp())
RUTA_BD = lambda: _tmpdir / "inicio.db"  # noqa: E731
ajustes.ruta_bd = RUTA_BD

from core import chequeo as C, expedientes as E, inicio as I  # noqa: E402


def _tr(tipo="construccion_urbana", modalidad="obra_nueva", dias_atras=0, responsable=None, **datos):
    eid = E.crear(dict(solicitante="Ana", clase_suelo="urbano", poligono="S1-CN-1", responsable=responsable), "f")
    tid = E.agregar_tramite(eid, tipo, modalidad, datos, "f", (date.today() - timedelta(days=dias_atras)).isoformat())
    return eid, tid


def test_tareas_por_perfil():
    con = {t["clave"] for t in I.tareas("consulta", "consulta")}
    fun = {t["clave"] for t in I.tareas("funcionario", "funcionario")}
    adm = {t["clave"] for t in I.tareas("administrador", "administrador")}
    assert "radicar" not in con and "norma" in con
    assert {"radicar", "documentos", "planos", "calcular", "informe", "norma"} == fun
    assert {"configuracion", "usuarios"} <= adm
    # un funcionario no puede ver la pantalla del administrador
    assert I.perfiles_visibles("funcionario") == ["consulta", "funcionario"]
    assert not {t["clave"] for t in I.tareas("administrador", "funcionario")} & {"configuracion", "usuarios"}


def test_pendientes_ordenados_y_siguiente_paso():
    _, t1 = _tr(dias_atras=0, n_pisos=3)
    _, t2 = _tr(dias_atras=90, responsable="ana", n_pisos=3)      # ya vencido
    lista = I.pendientes(limite=50)
    ids = [p["tramite_id"] for p in lista]
    assert ids.index(t2) < ids.index(t1)
    p2 = next(p for p in lista if p["tramite_id"] == t2)
    assert p2["nivel"] == "vencido" and p2["dias"] < 0
    assert p2["paso"]["pagina"] == "Listas de chequeo" and "documento" in p2["paso"]["texto"]
    mios = I.pendientes({"usuario": "ana", "nombre": "Ana Pérez"}, solo_mios=True, limite=50)
    assert [p["tramite_id"] for p in mios] == [t2]


def test_paso_despues_del_paquete():
    _, tid = _tr(tipo="nomenclatura_dian", modalidad="certificado")
    C.marcar_paquete(tid, True, "f", forzar=True, observacion="prueba")
    paso = I.siguiente_paso(E.tramite(tid))
    assert paso["pagina"] in ("Listas de chequeo", "Informes")
    _, tid2 = _tr(n_pisos=3)
    C.marcar_paquete(tid2, True, "f", forzar=True, observacion="prueba")
    assert I.siguiente_paso(E.tramite(tid2))["pagina"] == "Análisis de planos"


def test_buscador_unico():
    eid, _ = _tr()
    rad = E.obtener(eid)["radicado"]
    r = I.buscar(rad)
    assert r["tipo"] == "expedientes" and r["expedientes"][0]["id"] == eid
    r = I.buscar("s1-cn-1")
    assert r["tipo"] == "poligono" and r["ficha"]["codigo"] == "S1-CN-1"
    assert I.buscar("¿cuál es el retiro a quebradas?")["tipo"] == "norma"
    assert I.buscar("")["tipo"] == "vacio"


def test_avisos_llevan_a_una_pagina():
    for a in I.avisos():
        assert a["texto"] and a["pagina"]
