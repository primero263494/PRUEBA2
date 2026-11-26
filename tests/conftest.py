"""Cada archivo de pruebas usa su propia base y carpetas temporales. Al correr
toda la suite en un solo proceso, se vuelven a aplicar antes de cada módulo."""
import pytest


@pytest.fixture(autouse=True, scope="module")
def _rutas_del_modulo(request):
    from core import ajustes, borradores, calculadoras, chequeo, db, documentos, expedientes, informes, sesiones
    from core.planos import analisis
    mod = request.module
    if hasattr(mod, "RUTA_BD"):
        ajustes.ruta_bd = db.ruta_bd = mod.RUTA_BD        # db importa ruta_bd por nombre
        for m in (db, expedientes, documentos, chequeo, calculadoras, analisis, informes, sesiones, borradores):
            m.migrar()
    tmp = getattr(mod, "_tmpdir", None) or getattr(mod, "_TMP", None)
    if tmp is not None:
        documentos.EXPEDIENTES_DIR = tmp / ("expedientes" if hasattr(mod, "_tmpdir") else "exp")
        documentos.PAPELERA = tmp / ("papelera" if hasattr(mod, "_tmpdir") else "pap")
    yield
