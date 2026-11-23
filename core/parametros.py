"""Archivo de parámetros normativos.

Toda cifra que use el programa sale de aquí, con su norma y artículo.
Los valores base están en config/parametros/*.yaml (fácil de actualizar
cuando cambie la norma). Los cambios hechos desde el programa se guardan
aparte, en la tabla `parametros_override`, con usuario, fecha y motivo; así
siempre se puede ver el valor original del archivo y el que se está aplicando.

Claves: <alias>.<grupo>.<parametro>, por ejemplo
    pbot.cesiones_urbanas.tipo_b_porcentaje_area_neta
    tarifas.delineacion_m2.residencial_urbano_e3
    nsr10.amenaza_sismica_municipio.Aa
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import yaml

from core import auditoria, db
from core.rutas import PARAMETROS

# alias -> archivo
ARCHIVOS = {
    "nacional": "nacional.yaml",
    "pbot": "pbot_acuerdo_012_2017.yaml",
    "d152": "decreto_152_2018.yaml",
    "tarifas": "tarifas_decreto_001_2026.yaml",
    "nsr10": "nsr10.yaml",
}

# Orden de prevalencia para resolver conflictos (menor = prima)
PREVALENCIA = {"nacional": 0, "nsr10": 0, "pbot": 1, "d152": 2, "tarifas": 3}

_CAMPOS_BASE = {"valor", "unidad", "fuente", "nota", "opciones", "editable"}


@dataclass
class Parametro:
    clave: str
    valor: Any
    unidad: str | None = None
    fuente: str = ""
    nota: str | None = None
    opciones: list[dict] | None = None
    editable: bool = True
    origen: str = "archivo"          # archivo | modificado
    valor_archivo: Any = None
    modificacion: dict | None = None  # motivo, usuario, fecha
    extra: dict = field(default_factory=dict)

    @property
    def pendiente(self) -> bool:
        return self.valor is None or (self.nota or "").upper().startswith("PENDIENTE")

    def opcion_elegida(self) -> dict | None:
        if not self.opciones:
            return None
        for o in self.opciones:
            if str(o.get("id")) == str(self.valor):
                return o
        return None

    def valor_numerico(self):
        """Si es una lista de opciones con 'valor', devuelve el número elegido."""
        o = self.opcion_elegida()
        if o is not None and "valor" in o:
            return o["valor"]
        return self.valor

    def cita(self) -> str:
        return self.fuente


def _cita(fuente) -> str:
    if isinstance(fuente, dict):
        n, a = fuente.get("norma", ""), fuente.get("articulo", "")
        return f"{n}, art. {a}" if a else n
    return str(fuente or "")


def _es_parametro(nodo) -> bool:
    return isinstance(nodo, dict) and "valor" in nodo


@lru_cache(maxsize=1)
def _arbol() -> dict:
    arbol = {}
    for alias, archivo in ARCHIVOS.items():
        with open(PARAMETROS / archivo, encoding="utf-8") as f:
            arbol[alias] = yaml.safe_load(f) or {}
    return arbol


def recargar() -> None:
    """Llamar después de editar un .yaml a mano."""
    _arbol.cache_clear()


def _aplanar(nodo, prefijo="") -> dict[str, dict]:
    salida = {}
    if _es_parametro(nodo):
        salida[prefijo] = nodo
        return salida
    if isinstance(nodo, dict):
        for k, v in nodo.items():
            if k == "metadatos":
                continue
            salida.update(_aplanar(v, f"{prefijo}.{k}" if prefijo else str(k)))
    return salida


def _overrides() -> dict[str, dict]:
    filas = db.consultar("SELECT * FROM parametros_override")
    return {f["clave"]: f for f in filas}


def _construir(clave: str, nodo: dict, ov: dict | None) -> Parametro:
    p = Parametro(
        clave=clave,
        valor=nodo.get("valor"),
        unidad=nodo.get("unidad"),
        fuente=_cita(nodo.get("fuente")),
        nota=nodo.get("nota"),
        opciones=nodo.get("opciones"),
        editable=nodo.get("editable", True),
        valor_archivo=nodo.get("valor"),
        extra={k: v for k, v in nodo.items() if k not in _CAMPOS_BASE},
    )
    if ov is not None:
        p.valor = json.loads(ov["valor"])
        p.origen = "modificado"
        p.modificacion = {"motivo": ov["motivo"], "usuario": ov["usuario"], "fecha": ov["fecha"]}
    return p


def todos() -> dict[str, Parametro]:
    ovs = _overrides()
    planos = _aplanar(_arbol())
    return {c: _construir(c, n, ovs.get(c)) for c, n in planos.items()}


def obtener(clave: str) -> Parametro:
    planos = _aplanar(_arbol())
    if clave not in planos:
        raise KeyError(f"Parámetro no encontrado: {clave}")
    ov = db.consultar("SELECT * FROM parametros_override WHERE clave=?", (clave,))
    return _construir(clave, planos[clave], ov[0] if ov else None)


def valor(clave: str):
    """Atajo: devuelve el número/valor aplicado (resuelve listas de opciones)."""
    return obtener(clave).valor_numerico()


def metadatos(alias: str) -> dict:
    return _arbol()[alias].get("metadatos", {})


def modificar(clave: str, nuevo_valor, usuario: str, motivo: str) -> Parametro:
    """Cambia el valor aplicado de un parámetro. Exige motivo y queda auditado."""
    if not motivo or len(motivo.strip()) < 5:
        raise ValueError("Escriba el motivo del cambio (mínimo 5 caracteres), p. ej. el acto que lo soporta.")
    p = obtener(clave)
    if not p.editable:
        raise PermissionError(f"El parámetro {clave} no es editable.")
    if p.opciones:
        ids = [str(o.get("id")) for o in p.opciones]
        if str(nuevo_valor) not in ids:
            raise ValueError(f"Opción no válida. Elija una de: {', '.join(ids)}")
    db.ejecutar(
        "INSERT INTO parametros_override (clave, valor, motivo, usuario) VALUES (?,?,?,?) "
        "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor, motivo=excluded.motivo, "
        "usuario=excluded.usuario, fecha=datetime('now','localtime')",
        (clave, json.dumps(nuevo_valor, ensure_ascii=False), motivo.strip(), usuario),
    )
    auditoria.registrar(usuario, "editar", "parametro", clave,
                        antes={"valor": p.valor, "origen": p.origen},
                        despues={"valor": nuevo_valor}, motivo=motivo)
    return obtener(clave)


def restaurar(clave: str, usuario: str, motivo: str) -> Parametro:
    """Vuelve al valor del archivo .yaml."""
    p = obtener(clave)
    db.ejecutar("DELETE FROM parametros_override WHERE clave=?", (clave,))
    auditoria.registrar(usuario, "restaurar", "parametro", clave,
                        antes={"valor": p.valor}, despues={"valor": p.valor_archivo}, motivo=motivo)
    return obtener(clave)


def pendientes() -> list[Parametro]:
    return [p for p in todos().values() if p.pendiente]


def alertas_tarifas() -> list[Parametro]:
    """Tarifas cuyo valor del decreto es menor que el calculado (contradice el art. 2)."""
    salida = []
    for p in todos().values():
        if not p.clave.startswith("tarifas."):
            continue
        calc, dec = p.extra.get("calculado"), p.extra.get("decreto")
        if isinstance(calc, (int, float)) and isinstance(dec, (int, float)) and dec < calc:
            salida.append(p)
    return salida


def redondear_millar_superior(x: float) -> int:
    """Regla del art. 2 del Decreto 001 de 2026."""
    import math
    return int(math.ceil(x / 1000.0) * 1000)


def tarifa_m2(clave_tarifa: str) -> dict:
    """Devuelve la tarifa aplicada y las alternativas, según la regla elegida."""
    p = obtener(f"tarifas.delineacion_m2.{clave_tarifa}")
    uvt = valor("tarifas.bases.uvt")
    regla = obtener("tarifas.bases.regla_redondeo").valor
    exacto = round(p.extra["uvt"] * uvt, 2)
    if p.origen == "modificado":
        aplicado, base = p.valor, "valor modificado por la Secretaría"
    elif regla == "millar_superior":
        aplicado, base = redondear_millar_superior(exacto), "millar superior (art. 2)"
    elif regla == "sin_redondeo":
        aplicado, base = exacto, "UVT × factor sin redondeo"
    else:
        aplicado, base = p.extra.get("decreto", p.valor), "valor publicado en el decreto"
    return {
        "clave": clave_tarifa, "aplicado": aplicado, "criterio": base,
        "exacto": exacto, "decreto": p.extra.get("decreto"),
        "millar_superior": redondear_millar_superior(exacto),
        "nota": p.nota, "fuente": p.fuente,
    }


@lru_cache(maxsize=1)
def poligonos() -> list[dict]:
    ruta = PARAMETROS / str(_arbol()["pbot"]["aprovechamientos"]["tabla_poligonos"]["valor"])
    with open(ruta, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def poligono(codigo: str) -> dict | None:
    codigo = codigo.strip().upper()
    for fila in poligonos():
        if fila["codigo"].upper() == codigo:
            return fila
    return None
