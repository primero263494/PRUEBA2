"""Calculadoras normativas (módulo 6).

Cada cálculo devuelve pasos con fórmula, cifras y fuente, y se puede guardar
en el trámite para el informe (tabla `calculos`).
"""
from __future__ import annotations

import json

from core import auditoria, cesiones, db
from core import parametros as P

ESQUEMA = """
CREATE TABLE IF NOT EXISTS calculos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tramite_id INTEGER REFERENCES tramites(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL,                 -- indices | cuadro_areas | cesiones | plusvalia | liquidacion
    entradas TEXT NOT NULL,
    resultado TEXT NOT NULL,
    usuario TEXT NOT NULL,
    fecha TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""
TOL = 0.01   # m² de tolerancia por redondeo en sumas


def migrar():
    db.migrar(ESQUEMA)


def _paso(concepto, formula, calculo, resultado, unidad="", fuente="", estado=None):
    return {"concepto": concepto, "formula": formula, "calculo": calculo, "resultado": resultado,
            "unidad": unidad, "fuente": fuente, "estado": estado}


def _pct(t):
    t = str(t).replace("%", "").strip()
    try:
        v = float(t)
    except ValueError:
        return None
    return v / 100 if v > 1 else v


def guardar(tramite_id: int | None, tipo: str, entradas: dict, resultado: dict, usuario: str) -> int:
    cid = db.ejecutar("INSERT INTO calculos (tramite_id, tipo, entradas, resultado, usuario) VALUES (?,?,?,?,?)",
                      (tramite_id, tipo, json.dumps(entradas, ensure_ascii=False, default=str),
                       json.dumps(resultado, ensure_ascii=False, default=str), usuario))
    auditoria.registrar(usuario, "crear", "calculo", cid, despues={"tramite_id": tramite_id, "tipo": tipo})
    return cid


def listar(tramite_id: int) -> list[dict]:
    filas = db.consultar("SELECT * FROM calculos WHERE tramite_id=? ORDER BY id DESC", (tramite_id,))
    for f in filas:
        f["entradas"], f["resultado"] = json.loads(f["entradas"]), json.loads(f["resultado"])
    return filas


# ------------------------------------------------------------- 6.2 IO / IC
def indices(area_lote: float, area_ocupada: float, pisos: list[float], area_excluida_ic: float = 0.0,
            poligono: str | None = None, uso: str = "lote_individual",
            io_planos: float | None = None, ic_planos: float | None = None, area_base_io: float | None = None) -> dict:
    """pisos: área construida de cada piso. uso: lote_individual | urbanismo."""
    if area_lote <= 0:
        raise ValueError("El área del lote debe ser mayor que cero.")
    f138 = P.obtener("pbot.aprovechamientos.tabla_poligonos").fuente
    base = P.obtener("pbot.definiciones.base_indice_ocupacion")
    area_io = area_base_io if (area_base_io and base.valor != "area_total_predio") else area_lote
    total = sum(pisos)
    io = area_ocupada / area_io
    ic = (total - area_excluida_ic) / area_lote
    pasos = [
        _paso("Área construida total", "Σ área por piso", " + ".join(f"{p:,.2f}" for p in pisos) or "0", round(total, 2), "m²",
              "Acuerdo 012 de 2017, art. 137 (área construida)"),
        _paso("Índice de ocupación (IO)", "Área ocupada en primer piso / área base",
              f"{area_ocupada:,.2f} / {area_io:,.2f}", round(io, 4), "", f"{base.fuente} · {base.opcion_elegida()['etiqueta']}"),
        _paso("Índice de construcción (IC)", "(Área construida − áreas excluidas) / área del lote",
              f"({total:,.2f} − {area_excluida_ic:,.2f}) / {area_lote:,.2f}", round(ic, 4), "",
              "Acuerdo 012 de 2017, art. 137; Decreto 152 de 2018, art. 39 par. 4"),
    ]
    resultado = {"io": round(io, 4), "ic": round(ic, 4), "area_construida": round(total, 2), "pisos": len(pisos)}
    if pisos and pisos[0] + TOL < area_ocupada:
        pasos.append(_paso("Coherencia", "Área del piso 1 ≥ área ocupada", f"{pisos[0]:,.2f} vs {area_ocupada:,.2f}",
                           "Revisar", "", "", "REVISAR"))
    fila = P.poligono(poligono) if poligono else None
    if fila:
        io_max = _pct(fila["io_urbanismos"] if uso == "urbanismo" else fila["io_lotes_individuales"])
        ic_max = float(fila["ic"]) if fila["ic"] not in ("N/A", "") else None
        if io_max is not None:
            pasos.append(_paso("IO máximo de la ficha", f"Polígono {fila['codigo']}", "", io_max, "", f138,
                               "CUMPLE" if io <= io_max + 1e-9 else "NO CUMPLE"))
        if ic_max is not None:
            pasos.append(_paso("IC máximo de la ficha", f"Polígono {fila['codigo']}", "", ic_max, "", f138,
                               "CUMPLE" if ic <= ic_max + 1e-9 else "NO CUMPLE"))
        base_pisos = float(fila["altura_base_pisos"]) if fila["altura_base_pisos"] not in ("N/A", "") else None
        if base_pisos:
            pasos.append(_paso("Pisos frente a la altura base", f"{len(pisos)} pisos", "", base_pisos, "pisos", f138,
                               "CUMPLE" if len(pisos) <= base_pisos else "REVISAR"))
        resultado.update(io_max=io_max, ic_max=ic_max,
                         cumple_io=io <= (io_max or 9) + 1e-9, cumple_ic=ic <= (ic_max or 99) + 1e-9)
    if io_planos is not None:
        d = io - io_planos
        pasos.append(_paso("Diferencia IO con planos", "IO calculado − IO declarado", f"{io:.4f} − {io_planos:.4f}",
                           round(d, 4), "", "", "CUMPLE" if abs(d) < 0.005 else "REVISAR"))
        resultado["dif_io_planos"] = round(d, 4)
    if ic_planos is not None:
        d = ic - ic_planos
        pasos.append(_paso("Diferencia IC con planos", "IC calculado − IC declarado", f"{ic:.4f} − {ic_planos:.4f}",
                           round(d, 4), "", "", "CUMPLE" if abs(d) < 0.005 else "REVISAR"))
        resultado["dif_ic_planos"] = round(d, 4)
    return {"pasos": pasos, "resultado": resultado}


# ------------------------------------------------------- 6.3 cuadro de áreas
def cuadro_areas(area_bruta: float, vial_principal: float = 0, redes_primarias: float = 0, proteccion: float = 0,
                 vias_locales: float = 0, viviendas: int = 0, area_otros_usos: float = 0, vis_vip: bool = False,
                 pisos: list[dict] | None = None, declarado: dict | None = None) -> dict:
    """pisos: [{'piso': '1', 'uso': 'residencial', 'privada': m², 'comun': m²}, …]
    declarado: totales que trae el plano para comparar (area_neta, area_util, area_construida, …)."""
    pisos = pisos or []
    ces = cesiones.urbanas(area_bruta, vial_principal, redes_primarias, proteccion, vias_locales, viviendas,
                           area_otros_usos, sum((p.get("privada", 0) + p.get("comun", 0)) for p in pisos),
                           None, viviendas >= 4, vis_vip)
    afectaciones = vial_principal + redes_primarias + proteccion
    filas = [
        {"concepto": "Área bruta", "m2": area_bruta, "fuente": "Decreto 1077, art. 2.2.1.1"},
        {"concepto": "(−) Sistema vial principal", "m2": vial_principal, "fuente": "Acuerdo 012, art. 137"},
        {"concepto": "(−) Redes primarias de servicios", "m2": redes_primarias, "fuente": "Acuerdo 012, art. 137"},
        {"concepto": "(−) Conservación y protección", "m2": proteccion, "fuente": "Acuerdo 012, art. 137"},
        {"concepto": "Área neta urbanizable", "m2": ces["area_neta"], "fuente": "Decreto 1077, art. 2.2.1.1"},
        {"concepto": "(−) Cesión tipo A (vías locales)", "m2": vias_locales, "fuente": "Acuerdo 012, art. 144 lit. a"},
        {"concepto": "(−) Cesión espacio público" + (" VIS/VIP" if vis_vip else " tipo B"), "m2": ces["tipo_b_o_ep"],
         "fuente": "Acuerdo 012, arts. 144–145"},
    ]
    if vis_vip:
        filas.append({"concepto": "(−) Cesión equipamiento VIS/VIP", "m2": ces["tipo_c_suelo"], "fuente": "Acuerdo 012, art. 145"})
    filas.append({"concepto": "Área útil", "m2": ces["area_util"], "fuente": "Decreto 1077, art. 2.2.1.1"})
    filas.append({"concepto": "Cesión tipo C (m² construidos de equipamiento)", "m2": ces["tipo_c_construida"],
                  "fuente": "Acuerdo 012, art. 144 lit. c"})

    por_piso = {}
    por_uso = {}
    privada = comun = 0.0
    for p in pisos:
        t = p.get("privada", 0) + p.get("comun", 0)
        por_piso[str(p.get("piso"))] = por_piso.get(str(p.get("piso")), 0) + t
        por_uso[p.get("uso", "sin uso")] = por_uso.get(p.get("uso", "sin uso"), 0) + t
        privada += p.get("privada", 0)
        comun += p.get("comun", 0)
    total_construida = privada + comun

    inconsistencias = []
    if afectaciones > area_bruta + TOL:
        inconsistencias.append("Las afectaciones superan el área bruta.")
    if ces["area_util"] < -TOL:
        inconsistencias.append("El área útil resulta negativa: revise cesiones y afectaciones.")
    if abs(sum(por_piso.values()) - total_construida) > TOL:
        inconsistencias.append("La suma por piso no coincide con el total construido.")
    for clave, calc in (("area_neta", ces["area_neta"]), ("area_util", ces["area_util"]),
                        ("area_construida", total_construida), ("cesion_b", ces["tipo_b_o_ep"]),
                        ("area_privada", privada), ("area_comun", comun)):
        if declarado and declarado.get(clave) not in (None, ""):
            d = float(declarado[clave]) - calc
            if abs(d) > TOL:
                inconsistencias.append(f"{clave.replace('_', ' ').capitalize()}: el plano declara {float(declarado[clave]):,.2f} m² "
                                       f"y el cálculo da {calc:,.2f} m² (diferencia {d:+,.2f} m²).")
    return {"filas": filas, "por_piso": por_piso, "por_uso": por_uso,
            "privada": round(privada, 2), "comun": round(comun, 2), "total_construida": round(total_construida, 2),
            "inconsistencias": inconsistencias, "pasos_cesiones": ces["pasos"]}


def cuadro_a_excel(c: dict, ruta, titulo: str = "Cuadro de áreas") -> str:
    import openpyxl
    from openpyxl.styles import Font
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Cuadro de áreas"
    ws.append([titulo])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])
    ws.append(["Concepto", "Área (m²)", "Fuente"])
    for f in c["filas"]:
        ws.append([f["concepto"], round(f["m2"], 2), f["fuente"]])
    ws.append([])
    ws.append(["Área construida por piso"])
    for k, v in c["por_piso"].items():
        ws.append([f"Piso {k}", round(v, 2)])
    ws.append(["Área construida por uso"])
    for k, v in c["por_uso"].items():
        ws.append([k, round(v, 2)])
    ws.append(["Área privada", c["privada"]])
    ws.append(["Área común", c["comun"]])
    ws.append(["Total construida", c["total_construida"]])
    if c["inconsistencias"]:
        ws.append([])
        ws.append(["Inconsistencias"])
        for i in c["inconsistencias"]:
            ws.append([i])
    for col, w in zip("ABC", (48, 16, 40)):
        ws.column_dimensions[col].width = w
    for fila in ws.iter_rows(min_row=4):
        if isinstance(fila[1].value, (int, float)):
            fila[1].number_format = "#,##0.00"
    wb.save(ruta)
    return str(ruta)


def cuadro_a_word(c: dict, ruta, titulo: str = "Cuadro de áreas") -> str:
    import docx
    from docx.shared import Pt
    d = docx.Document()
    d.add_heading(titulo, level=1)
    t = d.add_table(rows=1, cols=3)
    t.style = "Table Grid"
    for celda, texto in zip(t.rows[0].cells, ("Concepto", "Área (m²)", "Fuente")):
        celda.text = texto
    for f in c["filas"]:
        r = t.add_row().cells
        r[0].text, r[1].text, r[2].text = f["concepto"], f"{f['m2']:,.2f}", f["fuente"]
    d.add_heading("Área construida", level=2)
    t2 = d.add_table(rows=1, cols=2)
    t2.style = "Table Grid"
    t2.rows[0].cells[0].text, t2.rows[0].cells[1].text = "Concepto", "Área (m²)"
    for k, v in list(c["por_piso"].items()):
        r = t2.add_row().cells
        r[0].text, r[1].text = f"Piso {k}", f"{v:,.2f}"
    for k, v in c["por_uso"].items():
        r = t2.add_row().cells
        r[0].text, r[1].text = f"Uso: {k}", f"{v:,.2f}"
    for k, v in (("Área privada", c["privada"]), ("Área común", c["comun"]), ("Total construida", c["total_construida"])):
        r = t2.add_row().cells
        r[0].text, r[1].text = k, f"{v:,.2f}"
    if c["inconsistencias"]:
        d.add_heading("Inconsistencias", level=2)
        for i in c["inconsistencias"]:
            d.add_paragraph(i, style="List Bullet")
    for p in d.paragraphs:
        for run in p.runs:
            run.font.size = Pt(11)
    d.save(ruta)
    return str(ruta)


# -------------------------------------------------------------- 6.5 plusvalía
HECHOS = {
    "incorporacion_suelo_rural_a_expansion_o_suburbano": ("Incorporación de suelo rural a expansión urbana o suburbano", "75"),
    "cambio_o_modificacion_de_uso": ("Cambio o modificación del uso", "76"),
    "mayor_aprovechamiento_edificabilidad": ("Mayor aprovechamiento en edificabilidad", "77"),
}


def plusvalia(hecho: str, area_predio: float, cesiones_ep: float = 0.0, afectaciones: float = 0.0,
              precio_antes: float | None = None, precio_despues: float | None = None,
              precio_referencia: float | None = None, m2_adicionales: float | None = None,
              tasa_id: str | None = None, forma_pago: str = "dinero", factor_ipc: float = 1.0) -> dict:
    if hecho not in HECHOS:
        raise ValueError("Hecho generador no válido.")
    tasa_p = P.obtener("pbot.plusvalia.tasa_participacion")
    tasa_op = next((o for o in tasa_p.opciones if str(o["id"]) == str(tasa_id)), None) if tasa_id else tasa_p.opcion_elegida()
    tasa = float(tasa_op["valor"])
    nombre, art = HECHOS[hecho]
    pasos = []
    area_obj = area_predio - cesiones_ep - afectaciones
    pasos.append(_paso("Área objeto de la participación", "Área del predio − cesiones de espacio público − afectaciones",
                       f"{area_predio:,.2f} − {cesiones_ep:,.2f} − {afectaciones:,.2f}", round(area_obj, 2), "m²",
                       "Ley 388 de 1997, art. 78; Acuerdo 012 de 2017, art. 318"))
    if hecho == "mayor_aprovechamiento_edificabilidad":
        if precio_referencia is None or m2_adicionales is None:
            raise ValueError("Ingrese el precio de referencia por m² y los m² adicionales de edificación.")
        efecto_total = precio_referencia * m2_adicionales
        pasos.append(_paso("Mayor valor total", "Potencial adicional de edificación × precio de referencia",
                           f"{m2_adicionales:,.2f} m² × ${precio_referencia:,.0f}", round(efecto_total), "$",
                           "Ley 388 de 1997, art. 77 num. 2 y 3; Acuerdo 012 de 2017, art. 317"))
        efecto_m2 = efecto_total / area_obj if area_obj else 0
        pasos.append(_paso("Efecto plusvalía por m²", "Mayor valor total / área objeto",
                           f"${efecto_total:,.0f} / {area_obj:,.2f}", round(efecto_m2, 2), "$/m²",
                           "Ley 388 de 1997, art. 77 num. 3"))
    else:
        if precio_antes is None or precio_despues is None:
            raise ValueError("Ingrese el precio por m² antes y después de la acción urbanística.")
        efecto_m2 = precio_despues - precio_antes
        pasos.append(_paso("Mayor valor por m²", "Nuevo precio de referencia − precio antes de la acción",
                           f"${precio_despues:,.0f} − ${precio_antes:,.0f}", round(efecto_m2, 2), "$/m²",
                           f"Ley 388 de 1997, art. {art} num. 3"))
        efecto_total = efecto_m2 * area_obj
        pasos.append(_paso("Efecto plusvalía total", "Mayor valor por m² × área objeto",
                           f"${efecto_m2:,.0f} × {area_obj:,.2f}", round(efecto_total), "$", f"Ley 388 de 1997, art. {art} num. 3"))
    if efecto_total <= 0:
        pasos.append(_paso("Sin efecto plusvalía", "El mayor valor es cero o negativo", "", 0, "$", "", "INFO"))
    participacion = max(efecto_total, 0) * tasa
    pasos.append(_paso("Participación en plusvalía", "Tasa × efecto plusvalía total",
                       f"{tasa:.0%} × ${max(efecto_total, 0):,.0f}", round(participacion), "$",
                       f"Acuerdo 012 de 2017, art. 319 ({tasa_op['etiqueta']}); Ley 388 de 1997, art. 79"))
    if factor_ipc and factor_ipc != 1.0:
        participacion *= factor_ipc
        pasos.append(_paso("Ajuste por IPC", "Participación × factor IPC desde la firmeza del acto",
                           f"× {factor_ipc:.4f}", round(participacion), "$", "Ley 388 art. 79 par. 2; Acuerdo 012 art. 319"))
    descuentos = {"dinero": 0.0, "obras_o_suelo": P.valor("pbot.plusvalia.descuento_pago_en_obras_o_suelo"),
                  "titulos_anticipados": P.valor("pbot.plusvalia.descuento_titulos_anticipados")}
    desc = descuentos.get(forma_pago, 0.0)
    if desc:
        pasos.append(_paso("Descuento por forma de pago", f"{desc:.0%} del monto liquidado",
                           f"${participacion:,.0f} × (1 − {desc:.2f})", round(participacion * (1 - desc)), "$",
                           "Acuerdo 012 de 2017, art. 322"))
        participacion *= (1 - desc)
    return {"hecho": nombre, "tasa": tasa, "area_objeto": round(area_obj, 2), "efecto_m2": round(efecto_m2, 2),
            "efecto_total": round(efecto_total), "participacion": round(participacion), "pasos": pasos}


# ---------------------------------------------------- liquidación (manual 5)
REGLAS = {
    "obra_nueva": (1.0, "Tarifa completa"),
    "adicion_o_cambio_de_uso": (None, "tarifas.reglas_especiales.adicion_o_cambio_de_uso"),
    "reforma_sin_subdivision": (None, "tarifas.reglas_especiales.reforma_sin_subdivision"),
    "reforma_con_subdivision": (None, "tarifas.reglas_especiales.reforma_con_subdivision"),
    "cambio_techo_por_losa": (None, "tarifas.reglas_especiales.cambio_techo_por_losa"),
}


def liquidar_delineacion(lineas: list[dict]) -> dict:
    """lineas: [{'uso': clave de tarifas.delineacion_m2, 'm2': área, 'regla': clave de REGLAS}, …]
    Usos combinados se liquidan por separado (Decreto 001 de 2026)."""
    pasos, total = [], 0.0
    for ln in lineas:
        t = P.tarifa_m2(ln["uso"])
        factor, ref = REGLAS.get(ln.get("regla", "obra_nueva"), (1.0, ""))
        fuente_regla = ""
        if factor is None:
            pr = P.obtener(ref)
            factor, fuente_regla = pr.valor, pr.fuente
        valor = ln["m2"] * t["aplicado"] * factor
        total += valor
        pasos.append(_paso(f"Delineación — {ln['uso'].replace('_', ' ')}",
                           "m² × tarifa por m²" + (f" × {factor:.0%}" if factor != 1 else ""),
                           f"{ln['m2']:,.2f} × ${t['aplicado']:,.0f}" + (f" × {factor}" if factor != 1 else ""),
                           round(valor), "$", t["fuente"] + (f" · {fuente_regla}" if fuente_regla else ""),
                           "INFO" if not t["nota"] else "REVISAR"))
    return {"pasos": pasos, "total": round(total)}


def liquidar_expensa(tipo: str, area_neta: float = 0, unidades: int = 0) -> dict:
    smldv, smmlv = P.valor("tarifas.bases.smldv"), P.valor("tarifas.bases.smmlv")
    if tipo == "urbanizacion":
        f = P.obtener("tarifas.expensas.urbanizacion_fraccion_smldv_por_m2")
        v = f.valor * smldv * area_neta
        return {"pasos": [_paso("Licencia de urbanización", "10 % SMLDV × área neta urbanizable",
                                f"{f.valor} × ${smldv:,.2f} × {area_neta:,.2f}", round(v), "$", f.fuente)], "total": round(v)}
    if tipo == "parcelacion":
        f = P.obtener("tarifas.expensas.parcelacion_fraccion_smldv_por_m2")
        v = f.valor * smldv * area_neta
        return {"pasos": [_paso("Licencia de parcelación", "2,5 % SMLDV × área neta urbanizable",
                                f"{f.valor} × ${smldv:,.2f} × {area_neta:,.2f}", round(v), "$", f.fuente)], "total": round(v)}
    if tipo == "subdivision":
        f = P.obtener("tarifas.expensas.subdivision_smmlv_por_unidad")
        v = f.valor * smmlv * unidades
        return {"pasos": [_paso("Subdivisión", "1 SMMLV × unidad resultante", f"${smmlv:,.0f} × {unidades}",
                                round(v), "$", f.fuente)], "total": round(v)}
    raise ValueError("Tipo de expensa no válido.")
