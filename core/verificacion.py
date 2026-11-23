"""Verificación de un trámite contra la norma (módulo 2).

Devuelve una lista de ítems {item, estado, detalle, fuente}. Estados:
CUMPLE, NO CUMPLE, REVISAR (requiere criterio o autorización), NO VERIFICABLE
(falta un dato) e INFO. Todos los límites salen del archivo de parámetros.
"""
from __future__ import annotations

import re
from datetime import date

from core import calendario, consulta
from core import parametros as P

CUMPLE, NO_CUMPLE, REVISAR, NO_VERIF, INFO = "CUMPLE", "NO CUMPLE", "REVISAR", "NO VERIFICABLE", "INFO"


def _r(item, estado, detalle, fuente=""):
    return {"item": item, "estado": estado, "detalle": detalle, "fuente": fuente}


def _num(x):
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _pct(txt):
    t = str(txt).strip().replace("%", "")
    v = _num(t)
    return None if v is None else (v / 100 if v > 1 else v)


def _fecha(x):
    try:
        return date.fromisoformat(str(x)[:10]) if x else None
    except ValueError:
        return None


# --------------------------------------------------------------- bloques
def _obligatorios(exp, tr, cat):
    salida = []
    fuente = "Manual de trámites interno, cap. 4.1; Decreto 1077 de 2015, art. 2.2.6.1.2.1.7"
    req_exp = {"solicitante": "Solicitante", "matricula": "Matrícula inmobiliaria",
               "cedula_catastral": "Cédula catastral", "direccion": "Dirección del predio",
               "clase_suelo": "Clase de suelo"}
    faltan = [v for k, v in req_exp.items() if not exp.get(k)]
    if exp.get("autoriza_notificacion_correo") and not exp.get("correo"):
        faltan.append("Correo (autorizó notificación electrónica)")
    nombres = P.valor("tramites.campos")
    faltan += [nombres.get(c, {}).get("etiqueta", c) for c in cat.get("campos", [])
               if tr["datos"].get(c) in (None, "")]
    salida.append(_r("Campos obligatorios", NO_CUMPLE if faltan else CUMPLE,
                     ("Faltan: " + ", ".join(faltan)) if faltan else "Completos.", fuente))
    m = exp.get("matricula") or ""
    if m and not re.fullmatch(r"\d{3}-\d{1,8}", m.strip()):
        salida.append(_r("Formato de matrícula", REVISAR, f"'{m}' no tiene la forma ORIP-número (ej. 020-12345).", fuente))
    cc = re.sub(r"\D", "", exp.get("cedula_catastral") or "")
    if exp.get("cedula_catastral") and len(cc) not in (20, 30):
        salida.append(_r("Formato de cédula catastral", REVISAR,
                         f"Tiene {len(cc)} dígitos; el código predial nacional tiene 30 (20 en el formato anterior).", fuente))
    return salida


def _documentos(tr):
    salida = []
    dias = P.valor("tramites.general.vigencia_documentos_dias")
    fuente = P.obtener("tramites.general.vigencia_documentos_dias").fuente
    fr = _fecha(tr["fecha_radicacion"])
    from core import documentos
    for campo, nombre, tipo_doc in (("fecha_cert_tradicion", "Certificado de tradición", "cert_tradicion"),
                                    ("fecha_paz_salvo", "Paz y salvo predial", "paz_salvo")):
        f = _fecha(tr["datos"].get(campo)) or _fecha(documentos.fecha_documento(tr["id"], tipo_doc))
        if not f:
            salida.append(_r(nombre, NO_VERIF, "Sin fecha de expedición registrada.", fuente))
        else:
            edad = (fr - f).days
            salida.append(_r(nombre, CUMPLE if 0 <= edad <= dias else NO_CUMPLE,
                             f"Expedido {edad} días antes de la radicación (máx. {dias}).", fuente))
    return salida


def _indices(exp, tr, fila):
    d = tr["datos"]
    lote, ocup, const = _num(d.get("area_lote")), _num(d.get("area_ocupada_piso1")), _num(d.get("area_construida"))
    f138 = P.obtener("pbot.aprovechamientos.tabla_poligonos").fuente
    if not fila:
        return [_r("Índices IO / IC", NO_VERIF, "Falta el polígono de tratamiento del predio.", f138)]
    if not lote:
        return [_r("Índices IO / IC", NO_VERIF, "Falta el área del lote.", f138)]
    salida = []
    base_io = P.obtener("pbot.definiciones.base_indice_ocupacion")
    area_base = lote
    if base_io.valor != "area_total_predio" and _num(d.get("area_neta")):
        area_base = _num(d.get("area_neta"))
    es_urbanismo = tr["tipo"] in ("urbanizacion",)
    io_max = _pct(fila["io_urbanismos"] if es_urbanismo else fila["io_lotes_individuales"])
    if ocup is not None and io_max is not None:
        io = ocup / area_base
        salida.append(_r("Índice de ocupación", CUMPLE if io <= io_max + 1e-9 else NO_CUMPLE,
                         f"IO = {ocup:,.2f} / {area_base:,.2f} = {io:.2%} · máximo {io_max:.0%} "
                         f"({base_io.opcion_elegida()['etiqueta']})", f138))
    elif io_max is None:
        salida.append(_r("Índice de ocupación", REVISAR, f"El polígono {fila['codigo']} no tiene IO asignado (N/A).", f138))
    if ocup is not None and ocup > lote:
        salida.append(_r("Coherencia de áreas", NO_CUMPLE, "El área ocupada supera el área del lote.", f138))
    ic_poli = _num(fila["ic"])
    ic_param = P.obtener("pbot.indice_construccion_maximo")
    if const is not None and ic_poli is not None:
        excluida = _num(d.get("area_excluida_ic")) or 0.0
        ic = (const - excluida) / lote
        especial = max(float(o["valor"]) for o in ic_param.opciones)          # 4,0 del D152 art. 39 par. 7
        habilitada = ic_param.valor_numerico() > ic_poli                         # la Secretaría eligió la opción 4,0
        det = f"IC = ({const:,.2f} − {excluida:,.2f} excluidas) / {lote:,.2f} = {ic:.2f} · tabla del polígono {ic_poli:g}"
        if ic <= ic_poli + 1e-9:
            estado = CUMPLE
        elif ic <= especial + 1e-9:
            estado = REVISAR if habilitada else NO_CUMPLE
            det += (f"; cabe solo con autorización especial de Planeación (IC {especial:g}, D152 art. 39 par. 7)"
                    + ("" if habilitada else " — opción no habilitada en Parámetros"))
        else:
            estado = NO_CUMPLE
        salida.append(_r("Índice de construcción", estado, det, f"{f138} · {ic_param.fuente}"))
    if const is not None and ocup is not None and const < ocup:
        salida.append(_r("Coherencia de áreas", NO_CUMPLE, "El área construida es menor que la ocupada en primer piso.", f138))
    return salida


def _altura(tr, fila):
    d = tr["datos"]
    pisos, lote = _num(d.get("n_pisos")), _num(d.get("area_lote"))
    f138 = P.obtener("pbot.aprovechamientos.tabla_poligonos").fuente
    salida = []
    if fila and pisos is not None:
        base, adic = _num(fila["altura_base_pisos"]), _num(fila["altura_adicional_pisos"]) or 0
        if base is None:
            salida.append(_r("Altura", REVISAR, f"El polígono {fila['codigo']} no tiene altura asignada.", f138))
        elif pisos <= base:
            salida.append(_r("Altura", CUMPLE, f"{pisos:g} pisos ≤ {base:g} de altura base.", f138))
        else:
            tope = base + adic
            limite_8 = P.valor("pbot.aprovechamientos.pisos_maximos_lote_mayor_800")
            lote_8 = P.valor("pbot.aprovechamientos.area_lote_para_8_pisos")
            if lote and lote > lote_8:
                tope = max(tope, limite_8)
            estado = REVISAR if pisos <= tope else NO_CUMPLE
            salida.append(_r("Altura", estado,
                             f"{pisos:g} pisos > {base:g} base. Máximo con cargas generales o plusvalía: {tope:g}.",
                             f"{f138} (notas *** y ****)"))
    elif pisos is not None:
        salida.append(_r("Altura", NO_VERIF, "Falta el polígono de tratamiento.", f138))
    via = _num(d.get("seccion_via"))
    if via is not None and pisos is not None:
        p = P.obtener("d152.edificacion.via_menor_8m_altura_max")
        if via < 8 and pisos > p.valor["pisos"]:
            salida.append(_r("Altura por sección vial", NO_CUMPLE, f"Vía de {via:g} m: máximo {p.valor['pisos']} pisos.", p.fuente))
        elif 8 <= via < 10 and pisos >= 3:
            q = P.obtener("d152.edificacion.seccion_requerida_3_pisos_o_mas")
            salida.append(_r("Altura por sección vial", REVISAR,
                             f"Vía de {via:g} m: para 3 o más pisos debe conformar sección de {q.valor} m entre paramentos.", q.fuente))
    return salida


def _densidad(tr, fila):
    d = tr["datos"]
    viv = _num(d.get("n_viviendas"))
    area = _num(d.get("area_neta")) or _num(d.get("area_lote"))
    f138 = P.obtener("pbot.aprovechamientos.tabla_poligonos").fuente
    if viv is None or not area:
        return [_r("Densidad", NO_VERIF, "Faltan viviendas o área.", f138)] if viv is not None else []
    if not fila or _num(fila["densidad_viv_ha_basica"]) is None:
        return [_r("Densidad", NO_VERIF, "El polígono no tiene densidad asignada o no se indicó.", f138)]
    basica, adic = _num(fila["densidad_viv_ha_basica"]), _num(fila["densidad_adicional"]) or 0
    permitidas = basica * area / 10000
    con_adic = (basica + adic) * area / 10000
    estado = CUMPLE if viv <= round(permitidas) else (REVISAR if viv <= round(con_adic) else NO_CUMPLE)
    return [_r("Densidad", estado,
               f"{viv:g} viviendas en {area:,.2f} m² · permitidas {permitidas:.1f} ({basica:g} viv/ha)"
               + (f", con adicional {con_adic:.1f}" if adic else "") + ". Se redondea al entero (par. 1).",
               f"{f138} y par. 1")]


def _tipologia(tr, fila):
    d = tr["datos"]
    viv, lote, frente, pisos = (_num(d.get("n_viviendas")) or (1 if d.get("uso_principal") == "residencial" else None),
                                _num(d.get("area_lote")), _num(d.get("frente_lote")), _num(d.get("n_pisos")) or 0)
    tip = P.obtener("d152.tipologias_vivienda")
    if not viv or not lote:
        return []
    nombre = "unifamiliar" if viv == 1 else "bifamiliar" if viv == 2 else "trifamiliar" if viv == 3 else "multifamiliar"
    t = next(x for x in tip.valor if x["tipologia"] == nombre)
    salida = [_r(f"Lote mínimo {nombre}", CUMPLE if lote >= t["area_min"] else NO_CUMPLE,
                 f"Lote {lote:,.2f} m² · mínimo {t['area_min']} m².", tip.fuente)]
    if frente is not None:
        req = t["frente_min"] + (max(0, pisos - 5) * t.get("frente_adicional_por_piso_sobre_5", 0))
        salida.append(_r(f"Frente mínimo {nombre}", CUMPLE if frente >= req else NO_CUMPLE,
                         f"Frente {frente:g} m · mínimo {req:g} m.", tip.fuente))
    if fila:
        clave = {"unifamiliar": "UNI", "bifamiliar": "BI", "trifamiliar": "TRI", "multifamiliar": "MULTI"}[nombre]
        permitidas = fila["tipologia"].upper()
        if permitidas not in ("N/A", "") and clave not in permitidas:
            salida.append(_r("Tipología permitida en el polígono", NO_CUMPLE,
                             f"{nombre} no está en '{fila['tipologia']}'.",
                             P.obtener("pbot.aprovechamientos.tabla_poligonos").fuente))
    return salida


def _usos(exp, tr):
    uso = str(tr["datos"].get("uso_principal") or "").strip()
    area = exp.get("area_actividad")
    fuente = P.obtener("pbot.usos_urbanos.tabla_usos").fuente
    if not uso:
        return []
    if not area:
        return [_r("Uso permitido", NO_VERIF, "Falta el área de actividad del predio (residencial, comercio…).", fuente)]
    if uso.lower() == "residencial":
        cat = {"residencial": "P", "comercio_servicios": "C", "artesanal": "C", "uso_social_obligado": "PH"}.get(area)
        return [_r("Uso permitido", CUMPLE if cat in ("P", "C") else NO_CUMPLE,
                   f"Vivienda en área {consulta.AREAS.get(area, area)}.", "Acuerdo 012 de 2017, art. 119")]
    filas = [r for r in consulta.tabla_usos() if r["clase"] == uso]
    if not filas:
        return [_r("Uso permitido", REVISAR, f"El código CIIU {uso} no está en la tabla; se entiende no permitido (par. 1).", fuente)]
    cat = filas[0][area]
    ley = consulta.leyenda()
    estado = {"P": CUMPLE, "C": CUMPLE, "R": REVISAR, "PH": NO_CUMPLE, "SC": NO_CUMPLE}[cat]
    return [_r("Uso permitido", estado, f"CIIU {uso} ({filas[0]['descripcion'][:70]}) en área "
               f"{consulta.AREAS.get(area, area)}: {ley.get(cat, cat)}.", fuente)]


def _otros_usos(exp, tr):
    if exp.get("area_actividad") != "residencial":
        return []
    otros, total = _num(tr["datos"].get("area_otros_usos")), _num(tr["datos"].get("area_construida"))
    if otros is None or not total:
        return []
    mx = P.obtener("pbot.usos_urbanos.max_otros_usos_en_residencial")
    return [_r("Otros usos en área residencial", CUMPLE if otros / total <= mx.valor else NO_CUMPLE,
               f"{otros / total:.1%} del área construida · máximo {mx.valor:.0%} en nuevos desarrollos.", mx.fuente)]


def _rural(tr):
    d = tr["datos"]
    salida = []
    cat = d.get("categoria_rural")
    mapa = {"produccion": "pbot.rural.io_produccion_forestal_agropecuaria", "uso_sostenible": "pbot.rural.io_uso_sostenible",
            "turistico": "pbot.rural.io_turistico", "desarrollo_restringido": "pbot.rural.io_desarrollo_restringido",
            "area_protegida": "d152.rural.io_areas_protegidas_drmi_rfpr"}
    lote, ocup = _num(d.get("area_lote")), _num(d.get("area_ocupada_piso1"))
    if cat in mapa and lote and ocup is not None:
        p = P.obtener(mapa[cat])
        salida.append(_r("Índice de ocupación rural", CUMPLE if ocup / lote <= p.valor else NO_CUMPLE,
                         f"{ocup / lote:.2%} · máximo {p.valor:.0%} ({p.unidad}).", p.fuente))
    elif cat:
        salida.append(_r("Índice de ocupación rural", NO_VERIF, "Faltan áreas o la categoría no está en la lista.", ""))
    pisos = _num(d.get("n_pisos"))
    if pisos is not None:
        p = P.obtener("pbot.rural.pisos_vivienda")
        salida.append(_r("Altura rural (vivienda)", CUMPLE if pisos <= p.valor else NO_CUMPLE,
                         f"{pisos:g} pisos · máximo {p.valor} + mansarda.", p.fuente))
    return salida


def _plan_parcial(exp, fila):
    if exp.get("clase_suelo") == "expansion" or (fila and "desarrollo" in fila["tratamiento"].lower()):
        p = P.obtener("pbot.tratamientos_reglas.desarrollo")
        return [_r("Plan parcial", REVISAR, "Suelo de expansión o tratamiento de desarrollo: verifique plan parcial adoptado.", p.fuente)]
    return []


def _arqueologia(tr):
    lote = _num(tr["datos"].get("area_lote"))
    p = P.obtener("pbot.ambiental.arqueologia_preventiva_area_minima")
    if lote and lote >= p.valor:
        return [_r("Arqueología preventiva", REVISAR, f"Lote de {lote:,.0f} m² ≥ {p.valor:,} m²: exigir programa ICANH.", p.fuente)]
    return []


def _subdivision(exp, tr):
    n = _num(tr["datos"].get("n_unidades_resultantes"))
    if n is None:
        return []
    if exp.get("clase_suelo") in ("rural", "suburbano"):
        p = P.obtener("pbot.rural.subdivision_max_predios_sin_parcelacion")
        return [_r("Número de predios", CUMPLE if n <= p.valor else NO_CUMPLE,
                   f"{n:g} predios; con 5 o más se requiere licencia de parcelación.", p.fuente)]
    return []


def _reconocimiento(tr):
    f = _fecha(tr["datos"].get("fecha_conclusion_obra"))
    p = P.obtener("tramites.general.reconocimiento_fecha_limite_conclusion")
    if not f:
        return [_r("Antigüedad de la edificación", NO_VERIF, "Falta la fecha de conclusión de la obra.", p.fuente)]
    limite = date.fromisoformat(p.valor)
    return [_r("Antigüedad de la edificación", CUMPLE if f <= limite else NO_CUMPLE,
               f"Concluida el {f.isoformat()}; debe ser a más tardar el {limite.isoformat()}.", p.fuente)]


def _prorroga(tr):
    v = _fecha(tr["datos"].get("fecha_vencimiento_licencia"))
    fr = _fecha(tr["fecha_radicacion"])
    p = P.obtener("nacional.licencias.prorroga_meses")
    if not v:
        return [_r("Oportunidad de la prórroga", NO_VERIF, "Falta la fecha de vencimiento de la licencia.", p.fuente)]
    return [_r("Oportunidad de la prórroga", CUMPLE if fr < v else NO_CUMPLE,
               f"Radicada el {fr}; la licencia vence el {v}. Debe solicitarse antes del vencimiento.", p.fuente)]


def _estudio_suelos(tr):
    if tr["tipo"] not in ("construccion_urbana", "construccion_rural"):
        return []
    pisos = _num(tr["datos"].get("n_pisos"))
    if pisos is not None and pisos <= 2:
        p = P.obtener("nsr10.geotecnia.obligatoriedad")
        return [_r("Estudio de suelos", REVISAR,
                   "Vivienda de 1–2 pisos: la NSR-10 H.1.1.2 exige estudio geotécnico; el manual interno admite apique. "
                   "Aplique el criterio que defina la Secretaría.", p.fuente)]
    return []


def _termino(tr):
    lim = _fecha(tr.get("fecha_limite"))
    if not lim:
        return []
    restantes = calendario.dias_habiles_entre(date.today(), lim)
    vencido = date.today() > lim
    p = P.obtener("nacional.licencias.termino_resolver_dias_habiles")
    return [_r("Término para resolver", NO_CUMPLE if vencido else INFO,
               f"Vence el {lim.isoformat()} ({'vencido' if vencido else f'{restantes} días hábiles restantes'}).",
               p.fuente)]


def _documentos_cargados(exp, tr):
    from core import documentos
    try:
        f = documentos.faltantes(exp, tr)
    except Exception:
        return []
    faltan = [x["nombre"] for x in f if not x["cargado"]]
    fuente = "Manual de trámites interno, cap. 4.1 y 4.2"
    return [_r("Documentos exigidos", CUMPLE if not faltan else NO_CUMPLE,
               ("Completos (" + str(len(f)) + ").") if not faltan else
               f"Faltan {len(faltan)} de {len(f)}: " + "; ".join(faltan), fuente)]


# ------------------------------------------------------------- principal
def verificar(expediente: dict, tramite: dict) -> list[dict]:
    cat = P.valor("tramites.tipos").get(tramite["tipo"], {})
    fila = P.poligono(expediente["poligono"]) if expediente.get("poligono") else None
    v = set(cat.get("verificaciones", []))
    res = _obligatorios(expediente, tramite, cat)
    if "documentos" in v:
        res += _documentos(tramite)
        res += _documentos_cargados(expediente, tramite)
    if "plan_parcial" in v or expediente.get("clase_suelo") == "expansion":
        res += _plan_parcial(expediente, fila)
    if "indices" in v:
        res += _indices(expediente, tramite, fila)
    if "altura" in v:
        res += _altura(tramite, fila)
    if "densidad" in v:
        res += _densidad(tramite, fila)
    if "tipologia_lote" in v:
        res += _tipologia(tramite, fila)
    if "usos" in v:
        res += _usos(expediente, tramite)
    if "otros_usos_residencial" in v:
        res += _otros_usos(expediente, tramite)
    if "indices_rural" in v or "altura_rural" in v:
        res += _rural(tramite)
    if "arqueologia" in v or tramite["tipo"] in ("construccion_urbana",):
        res += _arqueologia(tramite)
    if "subdivision" in v:
        res += _subdivision(expediente, tramite)
    if "reconocimiento" in v:
        res += _reconocimiento(tramite)
    if "prorroga" in v:
        res += _prorroga(tramite)
    res += _estudio_suelos(tramite)
    res += _termino(tramite)
    return res


def resumen(resultados: list[dict]) -> dict:
    from collections import Counter
    c = Counter(r["estado"] for r in resultados)
    if c[NO_CUMPLE]:
        global_ = NO_CUMPLE
    elif c[REVISAR] or c[NO_VERIF]:
        global_ = REVISAR
    else:
        global_ = CUMPLE
    return {"global": global_, **c}
