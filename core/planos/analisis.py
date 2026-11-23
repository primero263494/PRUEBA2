"""Reglas por disciplina, cruce entre disciplinas y concepto borrador.

Entrada: resultados de `lectores.analizar` (uno por archivo), con los
valores que el revisor haya corregido. Salida: ítems {disciplina, item,
estado, detalle, norma, evidencia} y un concepto borrador.

El programa NO reemplaza la revisión estructural ni la geotécnica: verifica
coherencia, parámetros declarados y requisitos; el concepto lo firma el
profesional competente (Ley 400 de 1997).
"""
from __future__ import annotations

import json
from collections import Counter

from core import auditoria, calculadoras, db, sismo
from core import parametros as P

CUMPLE, NO_CUMPLE, REVISAR, NO_VERIF, INFO = "CUMPLE", "NO CUMPLE", "REVISAR", "NO VERIFICABLE", "INFO"
TOL_AREA = 0.01      # 1 % de diferencia admitida entre fuentes
TOL_ALTURA = 0.05    # m

DISC_ARQ = ("arquitectonico", "topografico")
ESQUEMA = """
CREATE TABLE IF NOT EXISTS analisis_planos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tramite_id INTEGER REFERENCES tramites(id) ON DELETE CASCADE,
    archivos TEXT NOT NULL,
    datos TEXT NOT NULL,
    resultados TEXT NOT NULL,
    concepto TEXT NOT NULL,
    usuario TEXT NOT NULL,
    fecha TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""


def migrar():
    db.migrar(ESQUEMA)


def _it(disc, item, estado, detalle, norma="", evidencia=""):
    return {"disciplina": disc, "item": item, "estado": estado, "detalle": detalle, "norma": norma, "evidencia": evidencia}


# ------------------------------------------------------------ consolidación
def consolidar(lecturas: list[dict]) -> dict:
    """disciplina -> clave -> lista de {valor, evidencia, nivel} (primero lo de lectura completa)."""
    salida: dict = {}
    for r in sorted(lecturas, key=lambda r: 0 if r["nivel"] == "completa" else 1):
        disc = r["disciplina"]
        for k, v in r["datos"].items():
            salida.setdefault(disc, {}).setdefault(k, []).append({**v, "nivel": r["nivel"], "archivo": r["archivo"]})
    return salida


def _v(c: dict, discs, clave):
    for d in (discs if isinstance(discs, (list, tuple)) else [discs]):
        if c.get(d, {}).get(clave):
            x = c[d][clave][0]
            return x["valor"], x["evidencia"]
    return None, ""


def _todos(c: dict, discs, clave):
    out = []
    for d in (discs if isinstance(discs, (list, tuple)) else [discs]):
        out += c.get(d, {}).get(clave, [])
    return out


def _diferencia(a, b):
    return abs(a - b) / max(abs(a), abs(b), 1e-9)


# -------------------------------------------------------------- arquitectura
def _arquitectura(c, exp, tr) -> list[dict]:
    res = []
    D = "Arquitectura"
    lote, ev_lote = _v(c, DISC_ARQ, "area_lote")
    lote_t = tr["datos"].get("area_lote") if tr else None
    if lote is None and lote_t:
        lote, ev_lote = float(lote_t), "Dato del trámite"
    if lote is not None and lote_t:
        dif = _diferencia(float(lote), float(lote_t))
        res.append(_it(D, "Área del lote: plano vs. trámite", CUMPLE if dif <= TOL_AREA else REVISAR,
                       f"Plano {lote:,.2f} m² · trámite {float(lote_t):,.2f} m² · diferencia {dif:.1%}",
                       "Manual 3.2 (coherencia de cuadro de áreas y linderos)", ev_lote))
    for clave, nombre in (("area_lote", "Área del lote"), ("area_construida", "Área construida"), ("n_pisos", "Número de pisos")):
        valores = _todos(c, DISC_ARQ, clave) + _todos(c, DISC_ARQ, f"{clave}_texto")
        nums = [(float(x["valor"]), x["evidencia"]) for x in valores if isinstance(x["valor"], (int, float))]
        if len(nums) >= 2:
            a = nums[0]
            b = max(nums[1:], key=lambda x: _diferencia(a[0], x[0]))      # la fuente que más se aleja
            dif = _diferencia(a[0], b[0])
            res.append(_it(D, f"{nombre}: coherencia entre fuentes ({len(nums)})", CUMPLE if dif <= TOL_AREA else NO_CUMPLE,
                           f"{a[0]:,.2f} vs. {b[0]:,.2f} (diferencia {dif:.1%})", "Manual 3.2; Acuerdo 012 de 2017, art. 137",
                           f"{a[1]} | {b[1]}"))
    ocup, ev_oc = _v(c, DISC_ARQ, "area_ocupada")
    pisos_area, _ = _v(c, DISC_ARQ, "areas_por_piso")
    construida, ev_c = _v(c, DISC_ARQ, "area_construida")
    if lote and ocup is not None and (pisos_area or construida):
        pisos = [float(v) for v in pisos_area.values()] if isinstance(pisos_area, dict) else [float(construida)]
        r = calculadoras.indices(float(lote), float(ocup), pisos, 0.0, exp.get("poligono") if exp else None)
        for p in r["pasos"]:
            if p.get("estado") in ("CUMPLE", "NO CUMPLE", "REVISAR"):
                res.append(_it(D, p["concepto"], p["estado"], f"{p['formula']}: {p['resultado']} · calculado "
                               f"IO {r['resultado']['io']:.2%}, IC {r['resultado']['ic']:.2f}", p["fuente"], ev_oc))
        io_decl, ev_io = _v(c, DISC_ARQ, "io_declarado")
        if io_decl is not None:
            dif = abs(r["resultado"]["io"] - float(io_decl))
            res.append(_it(D, "IO declarado vs. calculado", CUMPLE if dif < 0.005 else REVISAR,
                           f"Declarado {float(io_decl):.2%} · calculado {r['resultado']['io']:.2%}",
                           "Acuerdo 012 de 2017, art. 137", ev_io))
    elif lote or ocup:
        res.append(_it(D, "Índices IO / IC", NO_VERIF, "Faltan área del lote, área ocupada o áreas por piso.",
                       "Acuerdo 012 de 2017, arts. 137–138"))
    mps, ev_mp = _v(c, DISC_ARQ, "matriculas_profesionales")
    res.append(_it(D, "Firma y matrícula del arquitecto", CUMPLE if mps else REVISAR,
                   f"Matrículas encontradas: {', '.join(mps)}" if mps else "No se encontró matrícula profesional en los planos.",
                   "Manual 3.2; Ley 400 de 1997", ev_mp))
    return res


# --------------------------------------------------------------- estructura
def _estructura(c, exp, tr) -> list[dict]:
    res = []
    D = "Estructura"
    if "estructural" not in c:
        return [_it(D, "Información estructural", NO_VERIF, "No se cargaron memorias, modelos ni planos estructurales.",
                    "Ley 400 de 1997; NSR-10")]
    for k in ("Aa", "Av"):
        decl, ev = _v(c, "estructural", k)
        norma = P.valor(f"nsr10.amenaza_sismica_municipio.{k}")
        fuente = P.obtener(f"nsr10.amenaza_sismica_municipio.{k}").fuente
        if decl is None:
            res.append(_it(D, f"{k} declarado", NO_VERIF, f"No se encontró {k} en la memoria. Norma: {norma}.", fuente))
        else:
            res.append(_it(D, f"{k} declarado", CUMPLE if float(decl) >= norma - 1e-9 else NO_CUMPLE,
                           f"Memoria {decl} · NSR-10 para El Carmen de Viboral {norma}", fuente, ev))
    perfil, ev_p = _v(c, "estructural", "perfil_suelo")
    if perfil and perfil in "ABCDE":
        for k, f in (("Fa", sismo.Fa), ("Fv", sismo.Fv)):
            decl, ev = _v(c, "estructural", k)
            calc = f(perfil)
            if decl is not None:
                res.append(_it(D, f"{k} para perfil {perfil}", CUMPLE if abs(float(decl) - calc) <= 0.011 else REVISAR,
                               f"Memoria {decl} · tabla NSR-10 {calc}", f"NSR-10 Tabla A.2.4-{'3' if k == 'Fa' else '4'}", ev))
    grupo, ev_g = _v(c, "estructural", "grupo_uso")
    i_decl, ev_i = _v(c, "estructural", "I")
    if grupo and i_decl is not None:
        i_norma = P.valor("nsr10.coeficiente_importancia").get(grupo)
        res.append(_it(D, "Coeficiente de importancia", CUMPLE if i_norma and abs(float(i_decl) - i_norma) < 0.001 else NO_CUMPLE,
                       f"Grupo {grupo}: memoria I = {i_decl} · NSR-10 I = {i_norma}", "NSR-10 Tabla A.2.5-1", ev_i))
    deriva, ev_d = _v(c, "estructural", "deriva_max")
    lim = sismo.deriva_maxima("concreto")
    if deriva is None:
        res.append(_it(D, "Derivas", NO_VERIF, "No se encontraron derivas (memoria o tabla exportada).", "NSR-10 Tabla A.6.4-1"))
    else:
        res.append(_it(D, "Deriva máxima", CUMPLE if float(deriva) <= lim + 1e-9 else NO_CUMPLE,
                       f"{float(deriva):.2%} de hpi · límite {lim:.1%} (concreto, acero, madera; 0,5 % mampostería)",
                       "NSR-10 Tabla A.6.4-1", ev_d))
    fcs = [x for x in _todos(c, "estructural", "fc_mpa") if isinstance(x["valor"], (int, float))]
    if len({round(x["valor"], 1) for x in fcs}) > 1:
        res.append(_it(D, "f'c memoria vs. modelo", REVISAR, " · ".join(f"{x['valor']} MPa ({x['archivo']})" for x in fcs),
                       "Manual 3.3 (concordancia)", " | ".join(x["evidencia"] for x in fcs)))
    elif fcs:
        res.append(_it(D, "Resistencia del concreto f'c", INFO, f"{fcs[0]['valor']} MPa", "NSR-10 Título C", fcs[0]["evidencia"]))
    fys = [x for x in _todos(c, "estructural", "fy_mpa") if isinstance(x["valor"], (int, float))]
    if fys:
        res.append(_it(D, "Fluencia del acero fy", INFO if len({x["valor"] for x in fys}) == 1 else REVISAR,
                       " · ".join(f"{x['valor']} MPa ({x['archivo']})" for x in fys), "NSR-10 Título C", fys[0]["evidencia"]))
    mps, ev_mp = _v(c, "estructural", "matriculas_profesionales")
    res.append(_it(D, "Firma y matrícula del ingeniero", CUMPLE if mps else REVISAR,
                   f"Matrículas: {', '.join(mps)}" if mps else "No se encontró matrícula profesional en la memoria.",
                   "Ley 400 de 1997; D152 art. 73", ev_mp))
    return res


# ---------------------------------------------------------------- geotecnia
def _geotecnia(c, exp, tr) -> list[dict]:
    res = []
    D = "Geotecnia"
    pisos, _ = _v(c, DISC_ARQ + ("estructural",), "n_pisos")
    if pisos is None and tr:
        pisos = tr["datos"].get("n_pisos")
    if "geotecnico" not in c:
        estado = REVISAR if pisos and float(pisos) <= 2 else NO_VERIF
        return [_it(D, "Estudio geotécnico", estado,
                    "No se cargó estudio de suelos." + (" Vivienda de 1–2 pisos: aplique el criterio de la Secretaría "
                                                        "(NSR-10 H.1.1.2 frente al apique del manual)." if estado == REVISAR else ""),
                    P.obtener("nsr10.geotecnia.obligatoriedad").fuente)]
    if pisos:
        cat = sismo.categoria_unidad(int(float(pisos)))
        req = sismo.sondeos_minimos(cat)
        n, ev_n = _v(c, "geotecnico", "n_sondeos")
        prof, ev_pr = _v(c, "geotecnico", "profundidad_max_m")
        fuente = "NSR-10 Tablas H.3.1-1 y H.3.2-1"
        res.append(_it(D, f"Número de sondeos (categoría {cat})",
                       NO_VERIF if n is None else (CUMPLE if int(n) >= req["numero"] else NO_CUMPLE),
                       f"Estudio {n if n is not None else '—'} · mínimo {req['numero']}", fuente, ev_n))
        res.append(_it(D, f"Profundidad de exploración (categoría {cat})",
                       NO_VERIF if prof is None else (CUMPLE if float(prof) >= req["profundidad_m"] else NO_CUMPLE),
                       f"Estudio {prof if prof is not None else '—'} m · mínimo {req['profundidad_m']} m", fuente, ev_pr))
    else:
        res.append(_it(D, "Sondeos mínimos", NO_VERIF, "Falta el número de pisos para fijar la categoría.", "NSR-10 Tabla H.3.1-1"))
    cap, ev_cap = _v(c, "geotecnico", "capacidad_portante_kpa")
    res.append(_it(D, "Capacidad portante", INFO if cap is not None else REVISAR,
                   f"{cap} kPa" if cap is not None else "El estudio no reporta capacidad portante legible.", "NSR-10 Título H", ev_cap))
    nf, ev_nf = _v(c, "geotecnico", "nivel_freatico_m")
    res.append(_it(D, "Nivel freático", INFO if nf is not None else REVISAR,
                   str(nf) if nf is not None else "No se encontró información de nivel freático.", "NSR-10 Título H", ev_nf))
    cim, ev_cim = _v(c, "geotecnico", "tipo_cimentacion")
    res.append(_it(D, "Recomendación de cimentación", INFO if cim else REVISAR, cim or "No se encontró recomendación de cimentación.",
                   "NSR-10 Título H; manual 3.3", ev_cim))
    return res


# ------------------------------------------------------- cruce disciplinas
def _cruce(c, exp, tr) -> list[dict]:
    res = []
    D = "Cruce entre disciplinas"
    n_arq, ev_a = _v(c, DISC_ARQ, "n_pisos")
    n_est, ev_e = _v(c, "estructural", "n_pisos")
    if n_arq is not None and n_est is not None:
        res.append(_it(D, "Número de pisos: arquitectura vs. estructura", CUMPLE if int(n_arq) == int(n_est) else NO_CUMPLE,
                       f"Arquitectura {n_arq} · estructura {n_est}", "Manual 3.3 (concordancia interdisciplinaria)", f"{ev_a} | {ev_e}"))
    h_arq = _todos(c, DISC_ARQ, "alturas_entrepiso")
    h_est = _todos(c, "estructural", "alturas_entrepiso")
    if h_arq and h_est:
        a, e = h_arq[0]["valor"], h_est[0]["valor"]
        difs = [abs(x - y) for x, y in zip(a, e)]
        ok = len(a) == len(e) and all(d <= TOL_ALTURA for d in difs)
        res.append(_it(D, "Alturas de entrepiso: arquitectura vs. estructura", CUMPLE if ok else NO_CUMPLE,
                       f"Arquitectura {a} · estructura {e} (tolerancia {TOL_ALTURA} m)", "Manual 3.3",
                       f"{h_arq[0]['evidencia']} | {h_est[0]['evidencia']}"))
    p_est, ev_pe = _v(c, "estructural", "perfil_suelo")
    p_geo, ev_pg = _v(c, "geotecnico", "perfil_suelo")
    if p_est and p_geo:
        res.append(_it(D, "Perfil de suelo: memoria estructural vs. estudio de suelos", CUMPLE if p_est == p_geo else NO_CUMPLE,
                       f"Memoria perfil {p_est} · estudio perfil {p_geo}", "NSR-10 A.2.4 y Título H", f"{ev_pe} | {ev_pg}"))
    elif p_est or p_geo:
        res.append(_it(D, "Perfil de suelo", REVISAR, "Solo una de las dos fuentes declara el perfil de suelo.", "NSR-10 A.2.4"))
    a_arq, ev_aa = _v(c, DISC_ARQ, "area_construida")
    a_ifc = [x for x in _todos(c, "estructural", "area_construida")]
    if a_arq is not None and a_ifc:
        dif = _diferencia(float(a_arq), float(a_ifc[0]["valor"]))
        res.append(_it(D, "Área construida: arquitectura vs. modelo estructural", CUMPLE if dif <= TOL_AREA else REVISAR,
                       f"{a_arq} vs. {a_ifc[0]['valor']} m²", "Manual 3.3", f"{ev_aa} | {a_ifc[0]['evidencia']}"))
    return res


# ---------------------------------------------------- ambiental y cartografía
def _ambiental(c, exp, tr, lecturas) -> list[dict]:
    res = []
    D = "Ambiental y cartografía"
    lote, _ = _v(c, DISC_ARQ, "area_lote")
    lote = lote or (tr["datos"].get("area_lote") if tr else None)
    arq = P.obtener("pbot.ambiental.arqueologia_preventiva_area_minima")
    if lote and float(lote) >= arq.valor and tr and tr["tipo"] in ("urbanizacion", "parcelacion"):
        res.append(_it(D, "Arqueología preventiva", REVISAR, f"Lote {float(lote):,.0f} m² ≥ {arq.valor:,}: exigir ICANH.", arq.fuente))
    geom = None
    for r in lecturas:
        if r["disciplina"] == "sig" and r["datos"].get("geometria"):
            geom = ("archivo", r["datos"]["geometria"]["valor"])
            break
    if geom is None:
        pts, _ = _v(c, DISC_ARQ, "lote_puntos_9377")
        if pts:
            geom = ("puntos", pts)
    if geom is None:
        res.append(_it(D, "Cruce con cartografía (rondas, amenazas, áreas protegidas)", NO_VERIF,
                       "No hay polígono del predio: suba un archivo SIG o un DXF georreferenciado (MAGNA-SIRGAS Origen Nacional) "
                       "con la capa LOTE.", "PBOT arts. 19, 56–63, 265"))
        return res
    try:
        from core import cartografia
        if geom[0] == "archivo":
            predio = cartografia.leer_predio([geom[1]])
        else:
            import geopandas as gpd
            from shapely.geometry import Polygon
            predio = gpd.GeoDataFrame(geometry=[Polygon(geom[1])], crs=cartografia.CRS_TRABAJO)
        cruces = cartografia.cruzar_predio(predio)
    except Exception as e:
        res.append(_it(D, "Cruce con cartografía", NO_VERIF, f"No se pudo hacer el cruce: {e}", "PBOT arts. 19 y 265"))
        return res
    restrictivos = {"rondas_hidricas", "areas_protegidas", "riesgo", "mancha_inundacion_tr100", "estructura_ecologica"}
    amenazas = {"amenaza_movimiento_masa", "amenaza_inundacion", "amenaza_avenida_torrencial"}
    for cr in cruces:
        pct = sum(i["porcentaje"] or 0 for i in cr["intersecciones"])
        vals = ", ".join(sorted({i["valor"] for i in cr["intersecciones"] if i["valor"]}))
        if cr["rol"] in restrictivos:
            estado = NO_CUMPLE if cr["afecta"] else CUMPLE
        elif cr["rol"] in amenazas:
            estado = REVISAR if cr["afecta"] else CUMPLE
        else:
            estado = INFO
        detalle = (f"Afecta {pct:.1f} % del predio" + (f" ({vals})" if vals else "")) if cr["afecta"] else "No afecta el predio."
        if cr["rol"] == "tratamientos" and exp and exp.get("poligono") and vals and exp["poligono"] not in vals:
            estado, detalle = REVISAR, f"La capa indica {vals}; el expediente dice {exp['poligono']}."
        res.append(_it(D, cr["rol_descripcion"], estado, detalle,
                       "PBOT art. 265 (amenaza: estudios de detalle)" if cr["rol"] in amenazas else "PBOT art. 19; Acuerdo Cornare 251/2011",
                       f"Capa '{cr['capa']}' {cr['fuente'] or ''}".strip()))
    falt = cartografia.roles_faltantes()
    if falt:
        res.append(_it(D, "Capas no cargadas", NO_VERIF, ", ".join(cartografia.ROLES[f][0] for f in falt), "Cartografía PBOT"))
    return res


# --------------------------------------------------------------- principal
def evaluar(lecturas: list[dict], expediente: dict | None, tramite: dict | None) -> dict:
    c = consolidar(lecturas)
    items = (_arquitectura(c, expediente, tramite) + _estructura(c, expediente, tramite) +
             _geotecnia(c, expediente, tramite) + _cruce(c, expediente, tramite) +
             _ambiental(c, expediente, tramite, lecturas))
    cerrados = [r for r in lecturas if r["nivel"] == "cerrado"]
    for r in cerrados:
        items.append(_it("Formatos", f"Archivo {r['archivo']}", REVISAR, " ".join(r["avisos"]), "Decreto 1077, art. 2.2.6.1.2.1.7"))
    return {"items": items, "consolidado": c, "concepto": concepto(items, expediente, tramite)}


def concepto(items: list[dict], expediente: dict | None, tramite: dict | None) -> dict:
    cnt = Counter(i["estado"] for i in items)
    if cnt[NO_CUMPLE]:
        sugerido = "NO VIABLE EN EL ESTADO ACTUAL — requiere correcciones"
    elif cnt[REVISAR] or cnt[NO_VERIF]:
        sugerido = "VIABLE CON OBSERVACIONES — pendiente de verificación"
    else:
        sugerido = "VIABLE"
    por_disc: dict = {}
    for i in items:
        por_disc.setdefault(i["disciplina"], Counter())[i["estado"]] += 1
    observaciones = [f"{i['disciplina']} — {i['item']}: {i['detalle']} ({i['norma']})" for i in items if i["estado"] == NO_CUMPLE]
    pendientes = [f"{i['disciplina']} — {i['item']}: {i['detalle']}" for i in items if i["estado"] in (REVISAR, NO_VERIF)]
    rad = (expediente or {}).get("radicado", "")
    texto = (f"Revisados los planos y estudios del radicado {rad}, el análisis automático encontró "
             f"{cnt[CUMPLE]} ítems que cumplen, {cnt[NO_CUMPLE]} que no cumplen y {cnt[REVISAR] + cnt[NO_VERIF]} que "
             f"requieren verificación del revisor. Concepto sugerido: {sugerido}. Este es un borrador generado por el "
             "programa: no reemplaza la revisión estructural ni la geotécnica, y debe ser revisado y firmado por el "
             "profesional competente.")
    return {"sugerido": sugerido, "conteo": dict(cnt), "por_disciplina": {k: dict(v) for k, v in por_disc.items()},
            "observaciones": observaciones, "pendientes": pendientes, "texto": texto}


def guardar(tramite_id: int | None, lecturas: list[dict], resultado: dict, usuario: str) -> int:
    limpio = [{k: v for k, v in r.items() if k != "resumen"} for r in lecturas]
    aid = db.ejecutar("INSERT INTO analisis_planos (tramite_id, archivos, datos, resultados, concepto, usuario) VALUES (?,?,?,?,?,?)",
                      (tramite_id, json.dumps([r["archivo"] for r in lecturas], ensure_ascii=False),
                       json.dumps(limpio, ensure_ascii=False, default=str),
                       json.dumps(resultado["items"], ensure_ascii=False, default=str),
                       json.dumps(resultado["concepto"], ensure_ascii=False, default=str), usuario))
    auditoria.registrar(usuario, "crear", "analisis_planos", aid,
                        despues={"tramite_id": tramite_id, "concepto": resultado["concepto"]["sugerido"]})
    return aid


def ultimo(tramite_id: int) -> dict | None:
    f = db.consultar("SELECT * FROM analisis_planos WHERE tramite_id=? ORDER BY id DESC LIMIT 1", (tramite_id,))
    if not f:
        return None
    a = f[0]
    for k in ("archivos", "datos", "resultados", "concepto"):
        a[k] = json.loads(a[k])
    return a
