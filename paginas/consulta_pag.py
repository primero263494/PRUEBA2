"""Página: consulta normativa (módulo 1)."""
import pandas as pd
import streamlit as st

from core import cartografia, cesiones, consulta
from core import parametros as P
from paginas.comun import guardar_subidos

COLORES = {"P": "#e5f4e4", "C": "#e7f1fb", "R": "#f9eeda", "PH": "#fbebeb", "SC": "#f0efec"}


def _mostrar_ficha(ficha: dict):
    st.subheader(f"Ficha normativa · {ficha['codigo']}")
    if ficha["na"]:
        st.info("Este polígono no tiene aprovechamientos asignados en la tabla del art. 138 (N/A). "
                "Su desarrollo lo define el plan urbanístico integral o la norma de conservación.")
    for titulo, items in ficha["secciones"].items():
        with st.expander(titulo, expanded=titulo in ("Aprovechamientos", "Condición del tratamiento")):
            df = pd.DataFrame([{"Concepto": i["etiqueta"], "Valor": str(i["valor"]), "Fuente": i["fuente"],
                                "Nota": i["nota"] or ""} for i in items])
            st.dataframe(df, hide_index=True, use_container_width=True)


def _tab_ficha():
    polis = consulta.lista_poligonos()
    modo = st.radio("Buscar por", ["Código de polígono", "Predio (polígono en el mapa)"], horizontal=True)
    if modo.startswith("Código"):
        trat = st.multiselect("Filtrar por tratamiento", sorted({p["tratamiento"] for p in polis}))
        opciones = [p["codigo"] for p in polis if not trat or p["tratamiento"] in trat]
        codigo = st.selectbox("Polígono", opciones)
        if codigo:
            _mostrar_ficha(consulta.ficha_poligono(codigo))
        return
    capas = cartografia.capas_por_rol().get("tratamientos")
    if not capas:
        st.warning("Cargue primero la capa de tratamientos (Cartografía → Cargar capa, rol 'Polígonos de "
                   "tratamiento') indicando el campo que trae el código, p. ej. S1-CN-1.")
        return
    archivos = st.file_uploader("Polígono del predio", accept_multiple_files=True,
                                type=["zip", "shp", "shx", "dbf", "prj", "geojson", "json", "kml", "kmz", "gpkg"])
    if not archivos:
        return
    try:
        predio = cartografia.leer_predio(guardar_subidos(archivos))
        res = cartografia.cruzar_predio(predio, roles=["tratamientos"])
    except Exception as e:
        st.error(str(e))
        return
    codigos = [(i["valor"], i["porcentaje"]) for r in res for i in r["intersecciones"] if i["valor"]]
    if not codigos:
        st.warning("El predio no cae en ningún polígono de tratamiento cargado, o la capa no tiene campo clave.")
        return
    for cod, pct in sorted(codigos, key=lambda x: -(x[1] or 0)):
        st.caption(f"{cod}: {pct} % del predio")
        f = consulta.ficha_poligono(cod)
        if f:
            _mostrar_ficha(f)
        else:
            st.warning(f"El código '{cod}' de la capa no coincide con la tabla del art. 138.")


def _tab_usos():
    ley = consulta.leyenda()
    st.caption(" · ".join(f"**{k}** {v}" for k, v in ley.items()))
    c1, c2, c3 = st.columns([2, 1, 1])
    texto = c1.text_input("Actividad o código CIIU", placeholder="panadería, 1081, taller, hotel…")
    area = c2.selectbox("Área de actividad", ["(todas)"] + list(consulta.AREAS), format_func=lambda a: consulta.AREAS.get(a, a))
    cats = c3.multiselect("Categoría", list(ley), default=[])
    filas = consulta.buscar_usos(texto, None if area.startswith("(") else area, set(cats) or None)
    df = pd.DataFrame(filas)
    if df.empty:
        st.info("Sin resultados. Recuerde: un uso que no está en la tabla se entiende no permitido (art. 123 par. 1).")
        return
    df = df.rename(columns={"clase": "CIIU", "descripcion": "Actividad", **consulta.AREAS, "pagina": "Pág. PBOT"})
    st.dataframe(df.style.map(lambda v: f"background-color: {COLORES.get(v, '')}",
                              subset=list(consulta.AREAS.values())),
                 hide_index=True, use_container_width=True)
    st.caption(f"{len(df)} actividades · Fuente: {P.obtener('pbot.usos_urbanos.tabla_usos').fuente}. "
               "Licor: prohibido a menos de 100 m de instituciones educativas (art. 123 par. 2).")
    with st.expander("¿Qué es cada área de actividad?"):
        for k, v in P.valor("pbot.usos_urbanos.areas_actividad").items():
            st.markdown(f"- **{consulta.AREAS.get(k, k.capitalize())}**: {v}")
        st.caption(P.obtener("pbot.usos_urbanos.areas_actividad").fuente)


def _tabla_pasos(pasos):
    df = pd.DataFrame([{"Concepto": p["concepto"], "Fórmula": p["formula"], "Cálculo": p["calculo"],
                        "Resultado": p["resultado"], "Unidad": p["unidad"], "Fuente": p["fuente"],
                        "Nota": p["nota"] or ""} for p in pasos])
    st.dataframe(df, hide_index=True, use_container_width=True)


def _tab_cesiones():
    st.markdown(
        "**Tipos de cesión (PBOT art. 143):** **A** — vías, sección vial y redes del proyecto; "
        "**B** — suelo para zonas verdes, parques, plazas y plazoletas; **C** — aporte para construir equipamientos.")
    sub = st.radio("Caso", ["Urbano y expansión", "VIS / VIP", "Parcelación rural"], horizontal=True)
    if sub == "Parcelación rural":
        c1, c2, c3 = st.columns(3)
        ab = c1.number_input("Área bruta (m²)", value=20000.0, step=100.0)
        n = c2.number_input("Número de parcelas", value=6, step=1)
        resid = c3.checkbox("Uso residencial", value=True)
        r = cesiones.parcelacion(ab, int(n), resid)
        _tabla_pasos(r["pasos"])
        st.info(r["nota"])
        return
    e = cesiones.EJEMPLO_URBANO
    st.caption("Ejemplo resuelto: cambie los datos para ver el cálculo con su proyecto.")
    c1, c2, c3, c4 = st.columns(4)
    ab = c1.number_input("Área bruta (m²)", value=e["area_bruta"], step=50.0)
    vp = c2.number_input("Sistema vial principal (m²)", value=e["vial_principal"], step=10.0)
    rp = c3.number_input("Redes primarias (m²)", value=e["redes_primarias"], step=10.0)
    pr = c4.number_input("Protección / ronda (m²)", value=e["proteccion"], step=10.0)
    c1, c2, c3, c4 = st.columns(4)
    vl = c1.number_input("Vías locales del proyecto (m²)", value=e["vias_locales_proyecto"], step=10.0)
    viv = c2.number_input("Viviendas", value=e["viviendas"], step=1)
    ou = c3.number_input("Área construida otros usos (m²)", value=e["area_construida_otros_usos"], step=10.0)
    tc = c4.number_input("Área total construida (m²)", value=e["area_total_construida"], step=50.0)
    multi = st.checkbox("Edificio multifamiliar", value=e["multifamiliar"])
    r = cesiones.urbanas(ab, vp, rp, pr, vl, int(viv), ou, tc, None, multi, vis_vip=(sub == "VIS / VIP"))
    _tabla_pasos(r["pasos"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Área neta", f"{cesiones.m2(r['area_neta'])} m²")
    c2.metric("Cesión espacio público", f"{cesiones.m2(r['tipo_b_o_ep'])} m²")
    c3.metric("Área útil resultante", f"{cesiones.m2(r['area_util'])} m²")
    an = r["area_neta_opciones"]
    with st.expander("Comparar las tres definiciones de área neta"):
        st.write({k: cesiones.m2(v) for k, v in an["valores"].items()})
        st.caption(f"Aplicada: {an['etiqueta']}. Se cambia en Parámetros → Opciones normativas.")

    st.subheader("Compensación en dinero o traslado")
    st.markdown(
        "- Procede cuando la cesión es menor a la exigida, su ubicación es inconveniente o hay espacio público "
        "prioritario; puede ser total o parcial sin afectar la funcionalidad del proyecto (PBOT art. 143 par. 1).\n"
        "- Tipo A: no menos del valor comercial del m² urbanizado en la zona homogénea. Tipo B: m² construido "
        "cubierto (CAMACOL o precio municipal) (art. 143 par. 1 lit. b).\n"
        "- Opciones: en sitio, en otro suelo para espacio público (parques lineales La Cimarronas y La Madera, "
        "déficit en otras comunidades) o en dinero (art. 146). Avalúo por Lonja con zonas geoeconómicas.\n"
        "- Destinación: fondo cuenta para espacio público y equipamientos (art. 147).\n"
        "- En suelo suburbano, vías y espacio público no se compensan en dinero (art. 253).")
    c1, c2, c3 = st.columns(3)
    tipo = c1.selectbox("Tipo", ["B", "A"])
    m = c2.number_input("m² a compensar", value=round(r["tipo_b_o_ep"] / 2, 2))
    v = c3.number_input("Valor de referencia $/m² (avalúo)", value=0.0, step=10000.0)
    comp = cesiones.compensacion(m, v or None, tipo)
    if comp["valor"] is None:
        st.warning(comp["mensaje"])
    else:
        st.metric("Valor de la compensación", f"${comp['valor']:,.0f}".replace(",", "."))
        st.caption(f"{comp['formula']} · {comp['fuente']}")


def _tab_suelo():
    tipo = st.radio("Tipo de suelo", ["urbano", "expansion", "suburbano", "rural"], horizontal=True,
                    format_func=lambda t: {"expansion": "Expansión"}.get(t, t.capitalize()))
    filas = consulta.parametros_por_suelo(tipo)
    st.dataframe(pd.DataFrame(filas).astype(str), hide_index=True, use_container_width=True)
    if tipo == "expansion":
        st.info("En suelo de expansión toda licencia exige plan parcial adoptado (PBOT art. 133).")


def _tab_buscar():
    q = st.text_input("Buscar en toda la norma", placeholder="retiro, ochava, S3-DU-7, plusvalía, 2.2.6.1.2.3.1")
    if not q:
        st.caption("Busca a la vez en parámetros, polígonos, usos del suelo y textos de normas cargadas.")
        return
    r = consulta.buscar(q)
    st.caption(f"{len(r['parametros'])} parámetros · {len(r['poligonos'])} polígonos · {len(r['usos'])} usos · "
               f"{len(r['articulos'])} artículos")
    if r["parametros"]:
        st.markdown("**Parámetros**")
        st.dataframe(pd.DataFrame(r["parametros"]).astype(str), hide_index=True, use_container_width=True)
    if r["poligonos"]:
        st.markdown("**Polígonos**")
        st.dataframe(pd.DataFrame(r["poligonos"]), hide_index=True, use_container_width=True)
    if r["usos"]:
        st.markdown("**Usos del suelo**")
        st.dataframe(pd.DataFrame(r["usos"]), hide_index=True, use_container_width=True)
    if r["articulos"]:
        st.markdown("**Artículos**")
        for a in r["articulos"]:
            with st.expander(f"{a['norma']} — art. {a['articulo']} {a['titulo'][:90]}"):
                st.text(a["texto"][:5000])
    elif not any(r.values()):
        st.info("Sin resultados. Si no ha importado los textos, vaya a Normas → Cargar normas base.")


def _tab_requisitos():
    """Requisitos documentales del listado de la Secretaría, con simulador de condiciones."""
    from core import documentos as D, expedientes as E
    st.caption("Listado de requisitos de la Secretaría de Planeación. Marque las condiciones del caso para ver "
               "exactamente qué documentos se exigen (estudio de suelos o apique, cámara de comercio, PH, etc.).")
    tipos = E.tipos()
    c1, c2, c3 = st.columns(3)
    tipo = c1.selectbox("Trámite", list(tipos), format_func=lambda k: tipos[k]["nombre"], key="req_tipo")
    modalidad = c2.selectbox("Modalidad", tipos[tipo]["modalidades"], key="req_mod")
    clase = c3.selectbox("Clase de suelo", ["urbano", "rural", "suburbano", "expansion"], key="req_clase",
                         index=1 if tipo == "construccion_rural" else 0)
    c1, c2, c3, c4 = st.columns(4)
    juridica = c1.checkbox("Persona jurídica", key="req_jur")
    datos = {"propiedad_horizontal": c2.checkbox("Propiedad horizontal", key="req_ph"),
             "apoderado": c3.checkbox("Tramita apoderado", key="req_apo"),
             "en_parcelacion": c4.checkbox("Predio en parcelación", key="req_parc")}
    c1, c2, c3, c4 = st.columns(4)
    datos["n_pisos"] = c1.number_input("Pisos", min_value=0, value=0, key="req_pisos") or None
    datos["area_construida"] = c2.number_input("Área a construir (m²)", min_value=0.0, value=0.0, key="req_area") or None
    datos["area_lote"] = c3.number_input("Área del lote (m²)", min_value=0.0, value=0.0, key="req_lote") or None
    datos["mansarda"] = c4.checkbox("Mansarda", key="req_mans")
    exp = {"tipo_persona": "juridica" if juridica else "natural", "clase_suelo": clase}
    tr = {"tipo": tipo, "modalidad": modalidad, "datos": {k: v for k, v in datos.items() if v}}
    lista = D.lista_secretaria(exp, tr)
    reqs = D.requisitos(exp, tr)
    if lista:
        st.markdown(f"**{lista[1]['titulo']}**")
        if lista[1].get("nota"):
            st.caption(lista[1]["nota"])
    else:
        st.info("Este trámite no está en el listado de la Secretaría; se muestran los documentos del manual de trámites.")
    vig = D.catalogo()
    st.dataframe(pd.DataFrame([{"N.º": i, "Documento": r["nombre"], "Obligatorio": "Si aplica" if r["opcional"] else "Sí",
                                "Vigencia": next((D.texto_vigencia(o) for o in r["tipo"].split("|") if D.tiene_vigencia(o)), ""),
                                "Nota": r["nota"]} for i, r in enumerate(reqs, 1)]), hide_index=True, use_container_width=True)
    st.caption(f"Fuente: {reqs[0]['fuente'] if reqs else ''}")


def mostrar():
    st.title("Consulta normativa")
    t = st.tabs(["Buscar", "Ficha por zona o predio", "Usos del suelo", "Cesiones", "Por tipo de suelo",
                 "Requisitos por trámite"])
    with t[5]:
        _tab_requisitos()
    with t[0]:
        _tab_buscar()
    with t[1]:
        _tab_ficha()
    with t[2]:
        _tab_usos()
    with t[3]:
        _tab_cesiones()
    with t[4]:
        _tab_suelo()
