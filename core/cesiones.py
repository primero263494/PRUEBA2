"""Cálculo explicado de cesiones urbanísticas.

Cada función devuelve una lista de pasos {concepto, formula, calculo,
resultado, unidad, fuente, nota} para mostrar el ejemplo resuelto y luego
usarlo en la calculadora y en los informes. Todos los porcentajes salen del
archivo de parámetros.
"""
from __future__ import annotations

from core import parametros as P


def _paso(concepto, formula, calculo, resultado, unidad, fuente, nota=None):
    return {"concepto": concepto, "formula": formula, "calculo": calculo,
            "resultado": round(resultado, 2) if isinstance(resultado, (int, float)) else resultado,
            "unidad": unidad, "fuente": fuente, "nota": nota}


def _f(clave):
    p = P.obtener(clave)
    return p.valor_numerico(), p.fuente


def m2(x: float) -> str:
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def area_neta(area_bruta: float, vial_principal: float = 0.0, redes_primarias: float = 0.0,
              proteccion: float = 0.0, retiros: float = 0.0, vias_obligadas: float = 0.0) -> dict:
    """Las tres definiciones vigentes en paralelo; devuelve también la elegida."""
    eleccion = P.obtener("pbot.definiciones.area_neta")
    pbot = area_bruta - vial_principal - redes_primarias - proteccion
    tarifas = area_bruta - retiros - vias_obligadas
    manual = area_bruta - vial_principal - redes_primarias - proteccion
    valores = {"pbot_art137": pbot, "decreto_tarifas_2026": tarifas, "manual_tramites": manual}
    return {"valores": valores, "elegida": eleccion.valor, "aplicada": valores[eleccion.valor],
            "etiqueta": eleccion.opcion_elegida()["etiqueta"], "fuente": eleccion.fuente}


def urbanas(area_bruta: float, vial_principal: float = 0.0, redes_primarias: float = 0.0,
            proteccion: float = 0.0, vias_locales_proyecto: float = 0.0, viviendas: int = 0,
            area_construida_otros_usos: float = 0.0, area_total_construida: float = 0.0,
            area_lote: float | None = None, multifamiliar: bool = False, vis_vip: bool = False) -> dict:
    """Cesiones en suelo urbano y de expansión (PBOT arts. 143–145)."""
    pasos = []
    an = area_neta(area_bruta, vial_principal, redes_primarias, proteccion)
    a_neta = an["valores"]["pbot_art137"]
    pasos.append(_paso(
        "Área neta urbanizable", "Área bruta − (vial principal + redes primarias + protección)",
        f"{m2(area_bruta)} − ({m2(vial_principal)} + {m2(redes_primarias)} + {m2(proteccion)})",
        a_neta, "m²", P.obtener("nacional.definiciones_decreto_1077.area_neta_urbanizable").fuente +
        " · Acuerdo 012 de 2017, art. 137",
        "No se descuentan cesiones, retiros a vías, laterales, de fondo ni a quebradas."))

    pasos.append(_paso(
        "Cesión tipo A (vías y redes)", "Sección pública completa de las vías del proyecto + plan vial + fajas de redes",
        "Se toma del diseño urbanístico (no es un porcentaje)", vias_locales_proyecto, "m²",
        "Acuerdo 012 de 2017, art. 144 lit. a",
        "Incluye calzada, andén y zona verde. Debe entregarse construida."))

    total_ep = total_eq_suelo = c_construida = 0.0
    if vis_vip:
        p_ep, f_ep = _f("pbot.cesiones_urbanas.vis_vip_espacio_publico")
        p_eq, f_eq = _f("pbot.cesiones_urbanas.vis_vip_equipamiento")
        total_ep, total_eq_suelo = a_neta * p_ep, a_neta * p_eq
        pasos.append(_paso("Cesión VIS/VIP para espacio público", f"{p_ep:.0%} × área neta",
                           f"{p_ep:.2f} × {m2(a_neta)}", total_ep, "m²", f_ep))
        pasos.append(_paso("Cesión VIS/VIP para equipamiento", f"{p_eq:.0%} × área neta",
                           f"{p_eq:.2f} × {m2(a_neta)}", total_eq_suelo, "m²", f_eq))
    else:
        p_b, f_b = _f("pbot.cesiones_urbanas.tipo_b_porcentaje_area_neta")
        p_sitio, f_sitio = _f("pbot.cesiones_urbanas.tipo_b_minimo_en_sitio")
        total_ep = a_neta * p_b
        pasos.append(_paso("Cesión tipo B (espacio público)", f"{p_b:.0%} × área neta",
                           f"{p_b:.2f} × {m2(a_neta)}", total_ep, "m²", f_b))
        pasos.append(_paso("— mínimo en sitio (parques, plazas, zonas verdes)", f"{p_sitio:.0%} × cesión B",
                           f"{p_sitio:.2f} × {m2(total_ep)}", total_ep * p_sitio, "m²", f_sitio,
                           "El resto se puede pagar para espacio público municipal (art. 146)."))
        c_viv, f_cv = _f("pbot.cesiones_urbanas.tipo_c_m2_por_vivienda")
        c_otros, f_co = _f("pbot.cesiones_urbanas.tipo_c_porcentaje_otros_usos")
        c_res = viviendas * c_viv
        c_no_res = area_construida_otros_usos * c_otros
        pasos.append(_paso("Cesión tipo C — vivienda (construcción de equipamiento)", f"{c_viv} m² × viviendas",
                           f"{c_viv} × {viviendas}", c_res, "m² construidos", f_cv))
        c_construida = c_res + c_no_res
        pasos.append(_paso("Cesión tipo C — otros usos", f"{c_otros:.1%} × área construida en otros usos",
                           f"{c_otros} × {m2(area_construida_otros_usos)}", c_no_res, "m² construidos", f_co))

    adicional_multi = 0.0
    lote_min, f_lm = _f("pbot.cesiones_urbanas.multifamiliar_lote_minimo")
    if multifamiliar and (area_lote or area_bruta) > lote_min:
        pct, f_pct = _f("pbot.cesiones_urbanas.multifamiliar_porcentaje_area_construida")
        adicional_multi = area_total_construida * pct
        pasos.append(_paso("Cesión de multifamiliar en lote > 300 m²", f"{pct:.0%} × área total construida",
                           f"{pct} × {m2(area_total_construida)}", adicional_multi, "m²", f_pct,
                           "Para usos comunales, institucionales o espacio público; si no es viable, en dinero."))

    return {"pasos": pasos, "area_neta": a_neta, "area_neta_opciones": an,
            "tipo_a": vias_locales_proyecto, "tipo_b_o_ep": total_ep,
            "tipo_c_suelo": total_eq_suelo, "tipo_c_construida": c_construida,
            "multifamiliar": adicional_multi,
            "area_util": a_neta - vias_locales_proyecto - total_ep - (total_eq_suelo if vis_vip else 0)}


def parcelacion(area_bruta: float, parcelas: int, residencial: bool = True) -> dict:
    """Cesiones en licencia de parcelación rural (PBOT art. 257; D152 arts. 140–141)."""
    pasos = []
    if residencial:
        b, fb = _f("pbot.rural.cesion_parcelacion_tipo_b")
        c, fc = _f("pbot.rural.cesion_parcelacion_tipo_c_suelo")
        m, fm = _f("pbot.rural.cesion_parcelacion_tipo_c_m2_por_parcela")
    else:
        b, fb = _f("pbot.rural.cesion_no_residencial_tipo_b")
        c, fc = _f("pbot.rural.cesion_no_residencial_tipo_c_suelo")
        m, fm = 0, ""
    pasos.append(_paso("Cesión tipo A", "Vías nacionales, departamentales o municipales con reservas y retiros",
                       "Según trazado; calzada construida con andenes y cunetas", "—", "", fb))
    pasos.append(_paso("Cesión tipo B", f"{b:.0%} × área bruta", f"{b} × {m2(area_bruta)}", area_bruta * b, "m²", fb))
    pasos.append(_paso("Cesión tipo C — suelo", f"{c:.0%} × área bruta", f"{c} × {m2(area_bruta)}", area_bruta * c, "m²", fc))
    if residencial:
        pasos.append(_paso("Cesión tipo C — edificación", f"{m} m² × parcelas", f"{m} × {parcelas}",
                           m * parcelas, "m² construidos", fm, "Se liquida y se destina a equipamientos comunitarios."))
    nota = "En suelo suburbano las cesiones de vías y espacio público no se compensan en dinero (art. 253)."
    return {"pasos": pasos, "nota": nota}


def compensacion(m2_a_compensar: float, valor_m2: float | None, tipo: str) -> dict:
    """Valor de compensación en dinero. Si no hay valor de referencia, lo pide."""
    clave = {"A": "pbot.cesiones_urbanas.valor_compensacion_tipo_a_m2",
             "B": "pbot.cesiones_urbanas.valor_compensacion_tipo_b_m2"}.get(tipo.upper())
    p = P.obtener(clave) if clave else None
    v = valor_m2 if valor_m2 is not None else (p.valor if p else None)
    if v is None:
        return {"valor": None, "mensaje": "Falta el valor de referencia por m² (parámetro pendiente). "
                                          "Ingréselo según avalúo de la Lonja o el decreto municipal.",
                "fuente": p.fuente if p else ""}
    return {"valor": round(m2_a_compensar * v, 0), "formula": f"{m2(m2_a_compensar)} m² × ${v:,.0f}",
            "fuente": p.fuente if p else ""}


# Ejemplo resuelto que se muestra por defecto en la consulta
EJEMPLO_URBANO = dict(area_bruta=5000.0, vial_principal=400.0, redes_primarias=0.0, proteccion=600.0,
                      vias_locales_proyecto=650.0, viviendas=40, area_construida_otros_usos=200.0,
                      area_total_construida=4200.0, multifamiliar=True)
