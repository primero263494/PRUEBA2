"""Página: calculadoras (módulo 6)."""
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from core import calc_cientifica, calculadoras as K, cesiones, db, expedientes as E
from core import parametros as P
from paginas.comun import puede, usuario

COLOR = {"CUMPLE": "#e5f4e4", "NO CUMPLE": "#fbebeb", "REVISAR": "#f9eeda", "INFO": "#e7f1fb"}


def _pesos(x):
    return f"${x:,.0f}".replace(",", ".")


def _tabla(pasos):
    df = pd.DataFrame([{"Concepto": p["concepto"], "Fórmula": p["formula"], "Cálculo": p["calculo"],
                        "Resultado": p["resultado"], "Unidad": p["unidad"], "Estado": p.get("estado") or "",
                        "Fuente": p["fuente"]} for p in pasos]).astype(str)
    st.dataframe(df.style.map(lambda v: f"background-color: {COLOR.get(v, '')}", subset=["Estado"]),
                 hide_index=True, use_container_width=True)


def _selector_tramite(clave: str):
    filas = db.consultar("SELECT t.id, t.tipo, e.radicado, e.poligono FROM tramites t "
                         "JOIN expedientes e ON e.id=t.expediente_id ORDER BY t.id DESC LIMIT 300")
    opciones = {0: "(sin trámite)"} | {f["id"]: f"#{f['id']} · {f['radicado']} · {E.tipos()[f['tipo']]['nombre']}" for f in filas}
    tid = st.selectbox("Trámite (opcional: para traer datos y guardar el cálculo)", list(opciones),
                       format_func=opciones.get, key=f"tr_{clave}")
    if not tid:
        return None, None, {}
    tr = E.tramite(tid)
    exp = E.obtener(tr["expediente_id"])
    return tid, exp, tr["datos"]


def _guardar(tid, tipo, entradas, resultado, clave):
    if tid and puede("calcular") and st.button("Guardar este cálculo en el trámite", key=f"g_{clave}"):
        K.guardar(tid, tipo, entradas, resultado, usuario()["usuario"])
        st.success("Cálculo guardado; quedará disponible para el informe.")


# --------------------------------------------------------------- científica
def _cientifica():
    s = st.session_state
    s.setdefault("calc_hist", [])
    s.setdefault("calc_mem", 0.0)
    s.setdefault("calc_ans", 0.0)
    c1, c2 = st.columns([3, 1])
    expr = c1.text_input("Expresión", key="calc_expr",
                         placeholder="Ej.: 2,5*120 + raiz(81) - 15%*200 · sen(30) · 3^4 · ans · m")
    grados = c2.radio("Ángulos", ["Grados", "Radianes"], horizontal=True) == "Grados"
    b = st.columns(6)
    if b[0].button("=", type="primary", use_container_width=True) and expr:
        try:
            r = calc_cientifica.evaluar(expr, grados, s["calc_ans"], s["calc_mem"])
            s["calc_ans"] = r
            s["calc_hist"].insert(0, (expr, r))
        except ValueError as e:
            st.error(str(e))
    if b[1].button("M+", use_container_width=True):
        s["calc_mem"] += s["calc_ans"]
    if b[2].button("M−", use_container_width=True):
        s["calc_mem"] -= s["calc_ans"]
    if b[3].button("MR → ans", use_container_width=True):
        s["calc_ans"] = s["calc_mem"]
    if b[4].button("MC", use_container_width=True):
        s["calc_mem"] = 0.0
    if b[5].button("Borrar historial", use_container_width=True):
        s["calc_hist"] = []
    r = s["calc_ans"]
    st.metric("Resultado (ans)", f"{r:,.10g}".replace(",", " "))
    st.caption(f"Memoria (m): {s['calc_mem']:,.10g}")
    st.caption("Funciones: raiz, raiz3, sen, cos, tan, asen, acos, atan, log, ln, exp, abs, redondear(x,n), fact, hipot; "
               "constantes pi, e; % (15% = 0,15); ^ potencia.")
    if s["calc_hist"]:
        st.dataframe(pd.DataFrame(s["calc_hist"][:30], columns=["Expresión", "Resultado"]), hide_index=True,
                     use_container_width=True)


# ------------------------------------------------------------------ IO / IC
def _indices():
    tid, exp, d = _selector_tramite("ind")
    polis = [""] + [p["codigo"] for p in P.poligonos()]
    pol_def = (exp or {}).get("poligono") or ""
    c1, c2, c3, c4 = st.columns(4)
    poligono = c1.selectbox("Polígono (ficha)", polis, index=polis.index(pol_def) if pol_def in polis else 0)
    lote = c2.number_input("Área del lote (m²)", min_value=0.0, value=float(d.get("area_lote") or 200.0))
    ocupada = c3.number_input("Área ocupada en primer piso (m²)", min_value=0.0, value=float(d.get("area_ocupada_piso1") or 160.0))
    uso = c4.radio("Caso", ["lote_individual", "urbanismo"], format_func=lambda x: x.replace("_", " ").capitalize())
    n = st.number_input("Número de pisos", 1, 30, int(d.get("n_pisos") or 3))
    base = pd.DataFrame({"Piso": [str(i + 1) for i in range(n)], "Área construida (m²)": [ocupada] * n})
    tabla = st.data_editor(base, hide_index=True, use_container_width=True, key=f"pisos_{n}")
    c1, c2, c3 = st.columns(3)
    excl = c1.number_input("Áreas excluidas del IC (balcones, parqueaderos, comunes…) (m²)", min_value=0.0,
                           value=float(d.get("area_excluida_ic") or 0.0))
    io_pl = c2.number_input("IO declarado en planos (0 si no aplica)", min_value=0.0, value=0.0, format="%.4f")
    ic_pl = c3.number_input("IC declarado en planos (0 si no aplica)", min_value=0.0, value=0.0, format="%.4f")
    if lote <= 0:
        st.info("Ingrese el área del lote.")
        return
    r = K.indices(lote, ocupada, [float(x) for x in tabla["Área construida (m²)"]], excl, poligono or None, uso,
                  io_pl or None, ic_pl or None)
    c1, c2 = st.columns(2)
    res = r["resultado"]
    c1.metric("IO", f"{res['io']:.2%}", None if res.get("io_max") is None else f"máx. {res['io_max']:.0%}", delta_color="off")
    c2.metric("IC", f"{res['ic']:.2f}", None if res.get("ic_max") is None else f"máx. {res['ic_max']:g}", delta_color="off")
    _tabla(r["pasos"])
    _guardar(tid, "indices", {"poligono": poligono, "lote": lote, "ocupada": ocupada,
                              "pisos": list(tabla["Área construida (m²)"]), "excluida": excl}, r, "ind")


# ----------------------------------------------------------- cuadro de áreas
def _cuadro():
    tid, exp, d = _selector_tramite("cua")
    c1, c2, c3, c4 = st.columns(4)
    ab = c1.number_input("Área bruta (m²)", min_value=0.0, value=float(d.get("area_lote") or 5000.0), key="cu_ab")
    vp = c2.number_input("Sistema vial principal (m²)", min_value=0.0, value=0.0, key="cu_vp")
    rp = c3.number_input("Redes primarias (m²)", min_value=0.0, value=0.0, key="cu_rp")
    pr = c4.number_input("Protección / rondas (m²)", min_value=0.0, value=0.0, key="cu_pr")
    c1, c2, c3, c4 = st.columns(4)
    vl = c1.number_input("Vías locales (cesión A) (m²)", min_value=0.0, value=0.0, key="cu_vl")
    viv = c2.number_input("Viviendas", min_value=0, value=int(d.get("n_viviendas") or 0), key="cu_viv")
    ou = c3.number_input("Área construida otros usos (m²)", min_value=0.0, value=float(d.get("area_otros_usos") or 0.0), key="cu_ou")
    vis = c4.checkbox("VIS / VIP", key="cu_vis")
    st.markdown("**Área construida por piso y por uso**")
    base = pd.DataFrame([{"piso": "1", "uso": "residencial", "privada": 0.0, "comun": 0.0}])
    pisos = st.data_editor(base, num_rows="dynamic", hide_index=True, use_container_width=True, key="cu_pisos",
                           column_config={"piso": "Piso", "uso": "Uso", "privada": "Área privada (m²)", "comun": "Área común (m²)"})
    with st.expander("Totales declarados en los planos (para detectar diferencias)"):
        c1, c2, c3 = st.columns(3)
        decl = {"area_neta": c1.number_input("Área neta", 0.0, key="cu_dn") or None,
                "area_util": c2.number_input("Área útil", 0.0, key="cu_du") or None,
                "area_construida": c3.number_input("Área construida total", 0.0, key="cu_dc") or None}
        c1, c2, c3 = st.columns(3)
        decl |= {"cesion_b": c1.number_input("Cesión B / espacio público", 0.0, key="cu_db") or None,
                 "area_privada": c2.number_input("Área privada", 0.0, key="cu_dp") or None,
                 "area_comun": c3.number_input("Área común", 0.0, key="cu_dco") or None}
    filas_p = [{k: (float(v) if k in ("privada", "comun") and not pd.isna(v) else (v if not pd.isna(v) else 0))
                for k, v in r.items()} for r in pisos.to_dict("records")]
    c = K.cuadro_areas(ab, vp, rp, pr, vl, int(viv), ou, vis, filas_p, decl)
    st.dataframe(pd.DataFrame([{"Concepto": f["concepto"], "Área (m²)": f"{f['m2']:,.2f}", "Fuente": f["fuente"]}
                               for f in c["filas"]]), hide_index=True, use_container_width=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("Área privada", f"{c['privada']:,.2f} m²")
    c2.metric("Área común", f"{c['comun']:,.2f} m²")
    c3.metric("Total construida", f"{c['total_construida']:,.2f} m²")
    if c["inconsistencias"]:
        for i in c["inconsistencias"]:
            st.warning(i)
    else:
        st.success("Sin inconsistencias de suma ni diferencias con lo declarado.")
    carpeta = Path(tempfile.mkdtemp())
    titulo = f"Cuadro de áreas{(' — ' + exp['radicado']) if exp else ''}"
    x = K.cuadro_a_excel(c, carpeta / "cuadro_areas.xlsx", titulo)
    w = K.cuadro_a_word(c, carpeta / "cuadro_areas.docx", titulo)
    c1, c2 = st.columns(2)
    c1.download_button("Exportar a Excel", Path(x).read_bytes(), "cuadro_areas.xlsx")
    c2.download_button("Exportar a Word", Path(w).read_bytes(), "cuadro_areas.docx")
    _guardar(tid, "cuadro_areas", {"area_bruta": ab, "vial": vp, "redes": rp, "proteccion": pr, "vias_locales": vl,
                                   "viviendas": viv, "otros_usos": ou, "vis": vis, "pisos": filas_p}, c, "cua")


# ----------------------------------------------------------------- cesiones
def _cesiones():
    tid, exp, d = _selector_tramite("ces")
    caso = st.radio("Caso", ["Urbano y expansión", "VIS / VIP", "Parcelación rural"], horizontal=True, key="ce_caso")
    if caso == "Parcelación rural":
        c1, c2, c3 = st.columns(3)
        ab = c1.number_input("Área bruta (m²)", value=float(d.get("area_lote") or 20000.0), key="ce_pab")
        n = c2.number_input("Parcelas", value=int(d.get("n_parcelas") or 6), key="ce_pn")
        res = c3.checkbox("Residencial", True, key="ce_pres")
        r = cesiones.parcelacion(ab, int(n), res)
        _tabla(r["pasos"])
        st.info(r["nota"])
        _guardar(tid, "cesiones", {"caso": caso, "area_bruta": ab, "parcelas": n, "residencial": res}, r, "ces")
        return
    c1, c2, c3, c4 = st.columns(4)
    ab = c1.number_input("Área bruta (m²)", value=float(d.get("area_lote") or 5000.0), key="ce_ab")
    vp = c2.number_input("Vial principal (m²)", value=0.0, key="ce_vp")
    rp = c3.number_input("Redes primarias (m²)", value=0.0, key="ce_rp")
    pr = c4.number_input("Protección (m²)", value=0.0, key="ce_pr")
    c1, c2, c3, c4 = st.columns(4)
    vl = c1.number_input("Vías locales (m²)", value=0.0, key="ce_vl")
    viv = c2.number_input("Viviendas", value=int(d.get("n_viviendas") or 0), key="ce_viv")
    ou = c3.number_input("Construido otros usos (m²)", value=float(d.get("area_otros_usos") or 0.0), key="ce_ou")
    tc = c4.number_input("Total construido (m²)", value=float(d.get("area_construida") or 0.0), key="ce_tc")
    multi = st.checkbox("Multifamiliar", value=int(viv) >= 4, key="ce_multi")
    r = cesiones.urbanas(ab, vp, rp, pr, vl, int(viv), ou, tc, None, multi, caso == "VIS / VIP")
    _tabla(r["pasos"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Área neta", f"{r['area_neta']:,.2f} m²")
    c2.metric("Cesión espacio público", f"{r['tipo_b_o_ep']:,.2f} m²")
    c3.metric("Área útil", f"{r['area_util']:,.2f} m²")
    _guardar(tid, "cesiones", {"caso": caso, "area_bruta": ab, "vial": vp, "redes": rp, "proteccion": pr,
                               "vias_locales": vl, "viviendas": viv, "otros_usos": ou, "total_construido": tc}, r, "ces")


# ---------------------------------------------------------------- plusvalía
def _plusvalia():
    tid, exp, d = _selector_tramite("plu")
    hecho = st.selectbox("Hecho generador", list(K.HECHOS), format_func=lambda h: K.HECHOS[h][0])
    tasa_p = P.obtener("pbot.plusvalia.tasa_participacion")
    ids = [str(o["id"]) for o in tasa_p.opciones]
    tasa = st.selectbox("Tasa de participación", ids, index=ids.index(str(tasa_p.valor)),
                        format_func=lambda i: next(o["etiqueta"] for o in tasa_p.opciones if str(o["id"]) == i))
    c1, c2, c3 = st.columns(3)
    area = c1.number_input("Área del predio (m²)", min_value=0.0, value=float(d.get("area_lote") or 1000.0))
    ces = c2.number_input("Cesiones de espacio público (m²)", min_value=0.0, value=0.0)
    afe = c3.number_input("Afectaciones plan vial / obras (m²)", min_value=0.0, value=0.0)
    if hecho == "mayor_aprovechamiento_edificabilidad":
        c1, c2, c3 = st.columns(3)
        pref = c1.number_input("Precio de referencia ($/m² construido, avalúo)", min_value=0.0, value=0.0, step=10000.0)
        modo = c2.radio("m² adicionales", ["Escribirlos", "Calcular con IC antes y después"])
        if modo == "Escribirlos":
            m2a = c3.number_input("Potencial adicional de edificación (m²)", min_value=0.0, value=0.0)
        else:
            ic0 = c3.number_input("IC antes", value=2.5)
            ic1 = c3.number_input("IC después", value=3.0)
            m2a = max(ic1 - ic0, 0) * (area - ces - afe)
            st.caption(f"m² adicionales = (IC después − IC antes) × área objeto = {m2a:,.2f} m²")
        datos = dict(precio_referencia=pref or None, m2_adicionales=m2a)
    else:
        c1, c2 = st.columns(2)
        pa = c1.number_input("Precio antes de la acción urbanística ($/m²)", min_value=0.0, value=0.0, step=10000.0)
        pd_ = c2.number_input("Nuevo precio de referencia ($/m²)", min_value=0.0, value=0.0, step=10000.0)
        datos = dict(precio_antes=pa, precio_despues=pd_)
    c1, c2 = st.columns(2)
    pago = c1.selectbox("Forma de pago", ["dinero", "obras_o_suelo", "titulos_anticipados"],
                        format_func={"dinero": "Dinero (sin descuento)", "obras_o_suelo": "Obras o suelo (5 %)",
                                     "titulos_anticipados": "Títulos anticipados (10 %)"}.get)
    ipc = c2.number_input("Factor de ajuste IPC (1 = sin ajuste)", min_value=0.0, value=1.0, format="%.4f")
    try:
        r = K.plusvalia(hecho, area, ces, afe, tasa_id=tasa, forma_pago=pago, factor_ipc=ipc, **datos)
    except ValueError as e:
        st.info(str(e))
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Efecto plusvalía por m²", _pesos(r["efecto_m2"]))
    c2.metric("Efecto total", _pesos(r["efecto_total"]))
    c3.metric("Participación a pagar", _pesos(r["participacion"]))
    _tabla(r["pasos"])
    st.caption("Los precios de referencia los fija el avalúo (IGAC, catastro o Lonja; Ley 388 art. 80). "
               "La plusvalía por mayor aprovechamiento aplica a multifamiliares y urbanismos (PBOT art. 138 par. 3).")
    _guardar(tid, "plusvalia", {"hecho": hecho, "tasa": tasa, "area": area, "cesiones": ces, "afectaciones": afe,
                                **datos, "pago": pago, "ipc": ipc}, r, "plu")


# -------------------------------------------------------------- liquidación
def _liquidacion():
    tid, exp, d = _selector_tramite("liq")
    st.markdown("**Impuesto de delineación urbana** (usos combinados se liquidan por separado)")
    usos = [c.split(".")[-1] for c in P.todos() if c.startswith("tarifas.delineacion_m2.")]
    base = pd.DataFrame([{"uso": "residencial_urbano_e3", "m2": float(d.get("area_construida") or 0.0), "regla": "obra_nueva"}])
    lineas = st.data_editor(base, num_rows="dynamic", hide_index=True, use_container_width=True, key="liq_lineas",
                            column_config={"uso": st.column_config.SelectboxColumn("Uso / clasificación", options=usos, required=True),
                                           "m2": st.column_config.NumberColumn("m²", min_value=0.0),
                                           "regla": st.column_config.SelectboxColumn("Caso", options=list(K.REGLAS), required=True)})
    lin = [r for r in lineas.to_dict("records") if r.get("uso") and r.get("m2")]
    total = 0
    if lin:
        r = K.liquidar_delineacion(lin)
        _tabla(r["pasos"])
        total += r["total"]
        st.metric("Delineación", _pesos(r["total"]))
    st.markdown("**Expensas**")
    c1, c2, c3 = st.columns(3)
    tipo = c1.selectbox("Actuación", ["(ninguna)", "urbanizacion", "parcelacion", "subdivision"])
    an = c2.number_input("Área neta urbanizable — definición tributaria: lote − retiros − vías obligadas (m²)", 0.0)
    un = c3.number_input("Unidades resultantes (subdivisión)", 0)
    if tipo != "(ninguna)":
        r2 = K.liquidar_expensa(tipo, an, int(un))
        _tabla(r2["pasos"])
        total += r2["total"]
    st.markdown("**Certificados y otras actuaciones** (tarifa fija)")
    otras = ["(ninguna)"] + list(K.otras_actuaciones())
    sugerida = K.TARIFA_SUGERIDA.get(E.tramite(tid)["tipo"]) if tid else None
    c1, c2 = st.columns([3, 1])
    otra = c1.selectbox("Tarifa", otras, index=otras.index(sugerida) if sugerida in otras else 0,
                        format_func=lambda k: k.replace("_", " ").capitalize(), key="liq_otra")
    cant = c2.number_input("Cantidad", 1, 1000, 1, key="liq_cant")
    if otra != "(ninguna)":
        r3 = K.liquidar_otra(otra, int(cant))
        _tabla(r3["pasos"])
        total += r3["total"]
    st.metric("Total liquidado", _pesos(total))
    st.caption(f"UVT {P.valor('tarifas.bases.uvt'):,} · SMMLV {P.valor('tarifas.bases.smmlv'):,} · "
               "Decreto 001 de 2026. Las tarifas con nota se revisan en Parámetros → Tarifas.")
    _guardar(tid, "liquidacion", {"lineas": lin, "expensa": tipo, "area_neta": an, "unidades": un, "otra": otra, "cantidad": cant}, {"total": total}, "liq")


def mostrar():
    st.title("Calculadoras")
    t = st.tabs(["Científica", "IO / IC", "Cuadro de áreas", "Cesiones", "Plusvalía", "Liquidación"])
    with t[0]:
        _cientifica()
    with t[1]:
        _indices()
    with t[2]:
        _cuadro()
    with t[3]:
        _cesiones()
    with t[4]:
        _plusvalia()
    with t[5]:
        _liquidacion()
