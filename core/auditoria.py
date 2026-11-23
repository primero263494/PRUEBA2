"""Registro de quién hizo cada cambio (requisito del programa)."""
import json

from core import db


def _json(x):
    return None if x is None else json.dumps(x, ensure_ascii=False, default=str)


def registrar(usuario: str, accion: str, entidad: str, entidad_id=None,
              antes=None, despues=None, motivo: str | None = None) -> int:
    return db.ejecutar(
        "INSERT INTO auditoria (usuario, accion, entidad, entidad_id, antes, despues, motivo)"
        " VALUES (?,?,?,?,?,?,?)",
        (usuario, accion, entidad, None if entidad_id is None else str(entidad_id),
         _json(antes), _json(despues), motivo),
    )


def listar(limite: int = 500, entidad: str | None = None, usuario: str | None = None) -> list[dict]:
    sql = "SELECT * FROM auditoria WHERE 1=1"
    params: list = []
    if entidad:
        sql += " AND entidad = ?"
        params.append(entidad)
    if usuario:
        sql += " AND usuario = ?"
        params.append(usuario)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limite)
    return db.consultar(sql, params)
