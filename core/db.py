"""Base de datos SQLite (biblioteca estándar de Python, sin instalar nada).

Tablas del módulo 0. Los módulos siguientes (expedientes, documentos,
listas de chequeo...) agregan sus tablas con la misma función `migrar`.
"""
import sqlite3
from contextlib import contextmanager

from core.ajustes import ruta_bd

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT UNIQUE NOT NULL,
    nombre TEXT NOT NULL,
    rol TEXT NOT NULL CHECK (rol IN ('consulta','funcionario','administrador')),
    hash TEXT NOT NULL,
    sal TEXT NOT NULL,
    activo INTEGER NOT NULL DEFAULT 1,
    creado TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS auditoria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    usuario TEXT NOT NULL,
    accion TEXT NOT NULL,          -- crear | editar | eliminar | cargar | ingresar ...
    entidad TEXT NOT NULL,         -- parametro | norma | capa | usuario | ajuste ...
    entidad_id TEXT,
    antes TEXT,                    -- JSON
    despues TEXT,                  -- JSON
    motivo TEXT
);

CREATE TABLE IF NOT EXISTS parametros_override (
    clave TEXT PRIMARY KEY,        -- ej. tarifas.delineacion_m2.residencial_urbano_e3
    valor TEXT NOT NULL,           -- JSON
    motivo TEXT NOT NULL,
    usuario TEXT NOT NULL,
    fecha TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS normas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    ambito TEXT NOT NULL,          -- nacional | municipal | ambiental | tecnica
    disciplina TEXT,               -- urbanistica | estructural | geotecnica | ambiental | tributaria
    version TEXT,
    archivo TEXT NOT NULL,
    texto TEXT,                    -- ruta al .txt extraído
    paginas INTEGER,
    metodo_lectura TEXT,           -- texto_digital | ocr_local | ia | sin_texto
    vigente INTEGER NOT NULL DEFAULT 1,
    verificado TEXT,               -- fecha de última verificación de vigencia
    cargado_por TEXT NOT NULL,
    fecha TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS normas_articulos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    norma_id INTEGER NOT NULL REFERENCES normas(id) ON DELETE CASCADE,
    articulo TEXT NOT NULL,
    titulo TEXT,
    texto TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS capas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    rol TEXT NOT NULL,             -- ver core.cartografia.ROLES
    archivo TEXT NOT NULL,
    formato TEXT NOT NULL,
    crs TEXT,
    n_elementos INTEGER,
    campo_clave TEXT,              -- atributo que identifica la zona (ej. CODIGO)
    fuente TEXT,                   -- ej. Plano CG_007 PBOT 2017
    cargado_por TEXT NOT NULL,
    fecha TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""


@contextmanager
def conexion():
    con = sqlite3.connect(ruta_bd())
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def migrar(esquema: str = ESQUEMA) -> None:
    with conexion() as con:
        con.executescript(esquema)


def consultar(sql: str, params=()) -> list[dict]:
    with conexion() as con:
        return [dict(f) for f in con.execute(sql, params).fetchall()]


def ejecutar(sql: str, params=()) -> int:
    with conexion() as con:
        cur = con.execute(sql, params)
        return cur.lastrowid
