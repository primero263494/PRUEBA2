"""Borradores de formularios largos (nuevo expediente, nuevo trámite).

Lo escrito se guarda en la base a medida que se llena, por usuario. Si la
página se recarga, se cambia de menú o se pierde la conexión, el formulario
vuelve con lo que había. Al crear el expediente el borrador se borra.
"""
from __future__ import annotations

import json

from core import db

ESQUEMA = """
CREATE TABLE IF NOT EXISTS borradores (
    usuario TEXT NOT NULL,
    clave TEXT NOT NULL,
    datos TEXT NOT NULL,
    fecha TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (usuario, clave)
);
"""


def migrar():
    db.migrar(ESQUEMA)


def guardar(usuario: str, clave: str, datos: dict) -> None:
    db.ejecutar("INSERT INTO borradores (usuario, clave, datos, fecha) VALUES (?,?,?,datetime('now','localtime')) "
                "ON CONFLICT(usuario, clave) DO UPDATE SET datos=excluded.datos, fecha=excluded.fecha",
                (usuario, clave, json.dumps(datos, ensure_ascii=False, default=str)))


def obtener(usuario: str, clave: str) -> dict | None:
    f = db.consultar("SELECT datos, fecha FROM borradores WHERE usuario=? AND clave=?", (usuario, clave))
    if not f:
        return None
    return {**json.loads(f[0]["datos"]), "_fecha_borrador": f[0]["fecha"]}


def borrar(usuario: str, clave: str) -> None:
    db.ejecutar("DELETE FROM borradores WHERE usuario=? AND clave=?", (usuario, clave))
