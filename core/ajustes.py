"""Lectura y escritura de config/ajustes.yaml."""
import copy
import yaml

from core.rutas import AJUSTES, BASE


def cargar() -> dict:
    with open(AJUSTES, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def guardar(ajustes: dict) -> None:
    with open(AJUSTES, "w", encoding="utf-8") as f:
        yaml.safe_dump(ajustes, f, allow_unicode=True, sort_keys=False)


def obtener(ruta: str, por_defecto=None):
    """obtener('lectura_escaneos.modo') -> 'auto'"""
    dato = cargar()
    for parte in ruta.split("."):
        if not isinstance(dato, dict) or parte not in dato:
            return por_defecto
        dato = dato[parte]
    return dato


def fijar(ruta: str, valor) -> dict:
    """Cambia un ajuste y devuelve (antes, después) para auditoría."""
    ajustes = cargar()
    antes = copy.deepcopy(ajustes)
    nodo = ajustes
    partes = ruta.split(".")
    for parte in partes[:-1]:
        nodo = nodo.setdefault(parte, {})
    nodo[partes[-1]] = valor
    guardar(ajustes)
    return {"antes": antes, "despues": ajustes}


def ruta_bd():
    return BASE / obtener("base_datos.ruta_sqlite", "datos/bd/tramites.db")
