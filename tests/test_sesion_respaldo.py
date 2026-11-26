"""Sesión que sobrevive a reconexiones, borradores y respaldo/restauración."""
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import ajustes  # noqa: E402

_tmpdir = Path(tempfile.mkdtemp())
RUTA_BD = lambda: _tmpdir / "sesion.db"  # noqa: E731
ajustes.ruta_bd = RUTA_BD

from core import auth, borradores, documentos as D, expedientes as E, respaldo, sesiones  # noqa: E402


@pytest.fixture(scope="module")
def admin():
    if not auth.hay_usuarios():
        auth.crear_usuario("admin", "Admin", "administrador", "clave-segura-1", "sistema")
    return auth.verificar("admin", "clave-segura-1")


def test_sesion_se_recupera_y_se_cierra(admin):
    t = sesiones.crear(admin["id"])
    assert sesiones.validar(t)["usuario"] == "admin"
    assert sesiones.validar("inventado") is None and sesiones.validar(None) is None
    sesiones.cerrar(t)
    assert sesiones.validar(t) is None


def test_sesion_de_usuario_inactivo_no_vale(admin):
    uid = auth.crear_usuario("pepe", "Pepe", "funcionario", "clave-segura-2", "admin")
    t = sesiones.crear(uid)
    auth.cambiar_estado(uid, False, "admin")
    assert sesiones.validar(t) is None


def test_base_creada_registrada():
    assert sesiones.base_creada()


def test_borradores():
    borradores.guardar("admin", "nuevo_expediente", {"solicitante": "Ana", "estrato": 3})
    b = borradores.obtener("admin", "nuevo_expediente")
    assert b["solicitante"] == "Ana" and b["_fecha_borrador"]
    borradores.guardar("admin", "nuevo_expediente", {"solicitante": "Ana María"})
    assert borradores.obtener("admin", "nuevo_expediente")["solicitante"] == "Ana María"
    assert borradores.obtener("otro", "nuevo_expediente") is None
    borradores.borrar("admin", "nuevo_expediente")
    assert borradores.obtener("admin", "nuevo_expediente") is None


def test_respaldo_y_restauracion(admin, monkeypatch):
    exp_dir = _tmpdir / "expedientes"
    monkeypatch.setattr(D, "EXPEDIENTES_DIR", exp_dir)
    monkeypatch.setitem(respaldo.CARPETAS, "datos/expedientes", exp_dir)
    monkeypatch.setitem(respaldo.CARPETAS, "datos/normas", _tmpdir / "normas")
    monkeypatch.setitem(respaldo.CARPETAS, "datos/capas", _tmpdir / "capas")
    monkeypatch.setitem(respaldo.CARPETAS, "config/plantillas", _tmpdir / "plantillas")
    eid = E.crear(dict(solicitante="Respaldo Uno", clase_suelo="urbano"), "admin")
    (exp_dir / "X").mkdir(parents=True, exist_ok=True)
    (exp_dir / "X" / "plano.pdf").write_bytes(b"%PDF prueba")
    contenido, nombre = respaldo.crear()
    assert nombre.endswith(".zip") and respaldo.validar(contenido)["archivos"] >= 1
    # se "pierde" todo: otro expediente nuevo y el archivo borrado
    E.crear(dict(solicitante="Después del respaldo", clase_suelo="urbano"), "admin")
    (exp_dir / "X" / "plano.pdf").unlink()
    respaldo.restaurar(contenido)
    nombres = [e["solicitante"] for e in E.listar()]
    assert "Respaldo Uno" in nombres and "Después del respaldo" not in nombres
    assert (exp_dir / "X" / "plano.pdf").read_bytes() == b"%PDF prueba"
    assert E.obtener(eid)


def test_respaldo_ajeno_se_rechaza():
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("algo.txt", "x")
    with pytest.raises(ValueError):
        respaldo.validar(buf.getvalue())
