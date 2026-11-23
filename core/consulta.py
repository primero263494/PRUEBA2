"""Consulta normativa: fichas por polígono, usos del suelo y buscador.

Todo resultado lleva su fuente (norma y artículo).
"""
from __future__ import annotations

import csv
import unicodedata
from functools import lru_cache

from core import normas
from core import parametros as P
from core.rutas import PARAMETROS

AREAS = {
    "uso_social_obligado": "Uso social obligado",
    "residencial": "Residencial",
    "comercio_servicios": "Comercio y servicios",
    "artesanal": "Artesanal",
}


def _sin_tildes(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def _item(etiqueta, valor, fuente, nota=None):
    return {"etiqueta": etiqueta, "valor": valor, "fuente": fuente, "nota": nota}


def _p(clave, etiqueta, formato=None, nota=None):
    p = P.obtener(clave)
    v = p.valor_numerico()
    if formato == "%":
        v = f"{v:.0%}" if isinstance(v, (int, float)) else v
    elif formato and isinstance(v, (int, float)):
        v = f"{v:g} {formato}"
    return _item(etiqueta, v, p.fuente, nota or p.nota)


def _tratamiento_clave(tratamiento: str) -> str:
    t = _sin_tildes(tratamiento)
    if "desarrollo" in t:
        return "desarrollo"
    if "conservacion" in t:
        return "conservacion"
    if "mejoramiento" in t:
        return "mejoramiento_integral"
    return "consolidacion"


# --------------------------------------------------------------- fichas
def ficha_poligono(codigo: str) -> dict | None:
    fila = P.poligono(codigo)
    if not fila:
        return None
    f138 = P.obtener("pbot.aprovechamientos.tabla_poligonos").fuente
    na = fila["densidad_viv_ha_basica"] in ("N/A", "")
    secciones = {}

    secciones["Identificación"] = [
        _item("Polígono", fila["codigo"], f138),
        _item("Sector", fila["sector"], f138),
        _item("Tratamiento", fila["tratamiento"], f138),
        _item("Tipologías permitidas", fila["tipologia"].replace("_", " ").replace("-", " "), f138),
    ]

    regla = P.obtener(f"pbot.tratamientos_reglas.{_tratamiento_clave(fila['tratamiento'])}")
    secciones["Condición del tratamiento"] = [_item("Regla", regla.valor, regla.fuente)]

    ic_max = P.obtener("pbot.indice_construccion_maximo")
    aprov = [
        _item("Densidad básica", f"{fila['densidad_viv_ha_basica']} viv/ha" if not na else "N/A", f138),
        _item("Densidad adicional", f"{fila['densidad_adicional']} viv/ha (con cargas generales o plusvalía)"
              if fila["densidad_adicional"] else "—", f138),
        _item("Altura base", f"{fila['altura_base_pisos']} pisos", f138),
        _item("Altura adicional", f"{fila['altura_adicional_pisos']} pisos (con cargas o plusvalía)", f138),
        _item("Índice de construcción (IC)", fila["ic"], f138,
              f"Máximo aplicado en el programa: {ic_max.valor_numerico()} ({ic_max.opcion_elegida()['etiqueta']})"),
        _item("Índice de ocupación — urbanismos", fila["io_urbanismos"], f138),
        _item("Índice de ocupación — lotes individuales", fila["io_lotes_individuales"], f138),
        _p("pbot.aprovechamientos.pisos_maximos_lote_mayor_800", "Altura máxima en lotes > 800 m²", "pisos"),
        _p("pbot.aprovechamientos.altura_unidad_piso_residencial", "Altura de un piso residencial", "m"),
        _p("pbot.aprovechamientos.semisotano_altura_maxima_sobre_anden", "Semisótano sobre el andén (máx.)", "m"),
    ]
    secciones["Aprovechamientos"] = aprov

    tip = P.obtener("d152.tipologias_vivienda")
    secciones["Lote mínimo y frente por tipología"] = [
        _item(t["tipologia"].capitalize(),
              f"{t['area_min']}–{t['area_max']} m², frente {t['frente_min']} m, {t['pisos']}", tip.fuente)
        for t in tip.valor
    ]

    secciones["Aislamientos y volumetría"] = [
        _p("d152.edificacion.retiro_medianeria_fachada_abierta", "Retiro a medianería, fachada abierta (4+ niveles)", "m"),
        _p("d152.edificacion.retiro_medianeria_fachada_semicerrada", "Retiro a medianería, fachada semicerrada", "m"),
        _p("d152.edificacion.retiro_medianeria_fachada_cerrada", "Retiro a medianería, fachada cerrada", "m"),
        _p("d152.edificacion.patio_lado_min", "Lado mínimo de patio", "m"),
        _p("d152.edificacion.mansarda_max_fraccion_piso_inferior", "Mansarda (máx. del piso inferior)", "%"),
        _p("d152.edificacion.via_menor_8m_altura_max", "Altura en vías de menos de 8 m"),
        _p("d152.edificacion.seccion_requerida_3_pisos_o_mas", "Sección vial para 3 o más pisos", "m"),
        _p("d152.edificacion.ascensor_desde_niveles", "Ascensor a partir de", "niveles"),
        _p("d152.edificacion.apartamento_area_min", "Área mínima de apartamento", "m²"),
    ]

    secciones["Cesiones que aplican"] = [
        _p("pbot.cesiones_urbanas.tipo_b_porcentaje_area_neta", "Tipo B (espacio público) sobre área neta", "%"),
        _p("pbot.cesiones_urbanas.tipo_c_m2_por_vivienda", "Tipo C por vivienda", "m²"),
        _p("pbot.cesiones_urbanas.tipo_c_porcentaje_otros_usos", "Tipo C otros usos (área construida)"),
        _p("pbot.cesiones_urbanas.multifamiliar_porcentaje_area_construida", "Multifamiliar en lote > 300 m²", "%"),
    ]

    secciones["Usos del suelo"] = [_item(
        "Usos", "Dependen del área de actividad del predio (residencial, comercio y servicios, artesanal, "
                "uso social obligado). Consulte la pestaña Usos del suelo o cruce el predio con la capa de usos.",
        P.obtener("pbot.usos_urbanos.tabla_usos").fuente)]
    return {"codigo": fila["codigo"], "secciones": secciones, "na": na}


def lista_poligonos() -> list[dict]:
    return P.poligonos()


# ----------------------------------------------------------------- usos
@lru_cache(maxsize=1)
def tabla_usos() -> list[dict]:
    ruta = PARAMETROS / str(P.obtener("pbot.usos_urbanos.tabla_usos").valor)
    with open(ruta, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def buscar_usos(texto: str = "", area: str | None = None, categorias: set[str] | None = None) -> list[dict]:
    t = _sin_tildes(texto.strip())
    salida = []
    for r in tabla_usos():
        if t and t not in _sin_tildes(r["descripcion"]) and not r["clase"].startswith(texto.strip()):
            continue
        if area and categorias and r[area] not in categorias:
            continue
        salida.append(r)
    return salida


def leyenda() -> dict:
    return P.valor("pbot.usos_urbanos.convenciones")


# ------------------------------------------------------- por tipo de suelo
def parametros_por_suelo(tipo: str) -> list[dict]:
    """tipo: urbano | expansion | rural | suburbano"""
    prefijos = {
        "urbano": ["pbot.aprovechamientos.", "pbot.cesiones_urbanas.", "d152.edificacion.", "d152.vias.", "d152.andenes."],
        "expansion": ["pbot.tratamientos_reglas.desarrollo", "pbot.cesiones_urbanas.", "pbot.aprovechamientos."],
        "rural": ["pbot.rural.", "d152.rural."],
        "suburbano": ["pbot.rural.densidad_suburbana", "pbot.rural.io_desarrollo_restringido",
                      "pbot.rural.io_industrial", "pbot.rural.aislamiento_comercio_suburbano",
                      "pbot.rural.suburbano_", "nacional.suelo_rural_suburbano."],
    }[tipo]
    return [{"clave": c, "valor": p.valor_numerico(), "unidad": p.unidad, "fuente": p.fuente, "nota": p.nota}
            for c, p in P.todos().items() if any(c.startswith(x) for x in prefijos)]


# ------------------------------------------------------------- buscador
def buscar(texto: str, limite: int = 60) -> dict:
    """Busca en parámetros, polígonos, usos y textos de normas cargadas."""
    t = _sin_tildes(texto.strip())
    if not t:
        return {"parametros": [], "poligonos": [], "usos": [], "articulos": []}
    params = []
    for c, p in P.todos().items():
        blob = _sin_tildes(" ".join(str(x) for x in (c, p.nota or "", p.fuente, p.unidad or "")))
        if t in blob or t.replace(" ", "_") in blob:
            params.append({"clave": c, "valor": p.valor_numerico(), "unidad": p.unidad,
                           "fuente": p.fuente, "nota": p.nota})
    polis = [f for f in P.poligonos() if t in _sin_tildes(" ".join(f.values()))]
    usos = buscar_usos(texto)[:limite]
    articulos = normas.buscar(texto, limite=limite)
    return {"parametros": params[:limite], "poligonos": polis, "usos": usos, "articulos": articulos}
