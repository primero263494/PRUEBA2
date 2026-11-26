"""Sesiones que sobreviven a una reconexión del navegador.

Streamlit guarda el usuario en la memoria de la pestaña. Si la conexión se
corta (red, servidor que se reinicia, pestaña suspendida), esa memoria se
pierde y el programa vuelve a pedir la contraseña. Para evitarlo, al ingresar
se crea un código aleatorio que queda en la dirección (?s=...) y en la base;
al reconectar, el programa lo lee y restaura al usuario.

El código vence a las 12 horas, se borra al salir y no contiene datos.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from core import db

DURACION_HORAS = 12
ESQUEMA = """
CREATE TABLE IF NOT EXISTS sesiones (
    token TEXT PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    creada TEXT NOT NULL,
    expira TEXT NOT NULL
);
"""


ESQUEMA += """
CREATE TABLE IF NOT EXISTS sistema (clave TEXT PRIMARY KEY, valor TEXT);
INSERT OR IGNORE INTO sistema (clave, valor) VALUES ('base_creada', datetime('now','localtime'));
"""


def migrar():
    db.migrar(ESQUEMA)


def base_creada() -> str:
    """Fecha en que se creó esta base de datos (sirve para detectar que el servidor la borró)."""
    f = db.consultar("SELECT valor FROM sistema WHERE clave='base_creada'")
    return f[0]["valor"] if f else ""


def crear(usuario_id: int) -> str:
    token = secrets.token_urlsafe(24)
    ahora = datetime.now()
    db.ejecutar("INSERT INTO sesiones (token, usuario_id, creada, expira) VALUES (?,?,?,?)",
                (token, usuario_id, ahora.isoformat(timespec="seconds"),
                 (ahora + timedelta(hours=DURACION_HORAS)).isoformat(timespec="seconds")))
    return token


def validar(token: str | None) -> dict | None:
    """Usuario activo dueño del código, si no ha vencido."""
    if not token:
        return None
    filas = db.consultar(
        "SELECT u.id, u.usuario, u.nombre, u.rol, s.expira FROM sesiones s JOIN usuarios u ON u.id=s.usuario_id "
        "WHERE s.token=? AND u.activo=1", (token,))
    if not filas or filas[0]["expira"] < datetime.now().isoformat(timespec="seconds"):
        return None
    f = filas[0]
    return {"id": f["id"], "usuario": f["usuario"], "nombre": f["nombre"], "rol": f["rol"]}


def cerrar(token: str | None) -> None:
    if token:
        db.ejecutar("DELETE FROM sesiones WHERE token=?", (token,))
    db.ejecutar("DELETE FROM sesiones WHERE expira < ?", (datetime.now().isoformat(timespec="seconds"),))
