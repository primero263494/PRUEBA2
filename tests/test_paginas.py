"""Dibuja cada página con un Streamlit simulado y datos de ejemplo: ninguna debe fallar."""
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import streamlit_simulado  # noqa: E402

st = streamlit_simulado.instalar()

from core import ajustes  # noqa: E402

_tmpdir = Path(tempfile.mkdtemp())
RUTA_BD = lambda: _tmpdir / "paginas.db"  # noqa: E731
ajustes.ruta_bd = RUTA_BD

from core import auth, calculadoras, chequeo, db, documentos as D, expedientes as E  # noqa: E402
from core.planos import analisis as A, lectores  # noqa: E402

PAGINAS = ["inicio", "expedientes", "documentos", "chequeo", "calculadoras", "consulta", "parametros", "normas",
           "cartografia", "planos", "informes", "configuracion", "usuarios", "auditoria"]


@pytest.fixture(scope="module", autouse=True)
def datos():
    if not auth.hay_usuarios():
        auth.crear_usuario("admin", "Admin Prueba", "administrador", "clave-segura-1", "sistema")
    eid = E.crear(dict(solicitante="Ana Pérez", clase_suelo="urbano", poligono="S1-CN-1", responsable="admin"), "admin")
    tid = E.agregar_tramite(eid, "construccion_urbana", "obra_nueva", {"area_lote": 200, "n_pisos": 3}, "admin")
    E.agregar_tramite(eid, "nomenclatura_dian", "certificado", {}, "admin")
    chequeo.generar(tid)
    calculadoras.guardar(tid, "indices", {}, calculadoras.indices(200, 160, [160, 160, 140], 0, "S1-CN-1"), "admin")
    ej = Path(__file__).parent / "ejemplos"
    lec = [lectores.analizar(f) for f in sorted(ej.iterdir()) if f.is_file()]
    A.guardar(tid, lec, A.evaluar(lec, E.obtener(eid), E.tramite(tid)), "admin")
    st.session_state.clear()
    st.session_state["usuario"] = {"id": 1, "usuario": "admin", "nombre": "Admin Prueba", "rol": "administrador"}
    st.session_state["tramite_foco"] = tid
    st.session_state["expediente_abierto"] = eid


@pytest.mark.parametrize("nombre", PAGINAS)
def test_pagina_se_dibuja(nombre):
    import importlib
    mod = importlib.import_module(f"paginas.{nombre}_pag")
    mod.mostrar()


@pytest.mark.parametrize("rol", ["consulta", "funcionario"])
def test_inicio_por_perfil(rol):
    from paginas import inicio_pag
    st.session_state["usuario"] = {"id": 1, "usuario": "u", "nombre": "U", "rol": rol}
    st.session_state.pop("vista_perfil", None)
    inicio_pag.mostrar()
    st.session_state["usuario"]["rol"] = "administrador"


def test_buscador_con_texto():
    from paginas import inicio_pag
    for texto in ("S1-CN-1", "Ana", "¿cuál es el retiro a quebradas?"):
        st.session_state["buscador_inicio"] = texto
        inicio_pag.mostrar()
    st.session_state["buscador_inicio"] = ""
