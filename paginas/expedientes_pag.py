"""Página: expedientes y trámites (módulo 2)."""
from datetime import date

import pandas as pd
import streamlit as st

from core import consulta, expedientes as E, verificacion as V
from core import parametros as P
from paginas.comun import confirmar_eliminacion, puede, usuario

COLOR = {V.CUMPLE: "#e5f4e4", V.NO_CUMPLE: "#fbebeb", V.REVISAR: "#f9eeda", V.NO_VERIF: "#f0efec", V.INFO: "#e7f1fb"}
AREAS = {"": "(sin definir)", **consulta.AREAS}
SUELOS = {"": "(sin definir)", "urbano": "Urbano", "expansion": "Expansión", "suburbano": "Suburbano", "rural": "Rural"}
CATEGORIAS_RURALES = {"": "(no aplica)", "produccion": "Producción forestal/agropecuaria", "uso_sostenible": "Uso sostenible",
                      "turistico": "Turístico", "desarrollo_restringido": "Desarrollo restringido",
                      "area_protegida": "RFPR / DRMI"}


def _form_expediente(prefijo: str, base: dict | None = None) -> dict:
    b = base or {}
    c1, c2, c3 = st.columns(3)
    datos = {
        "radicado": c1.text_input("Radicado", b.get("radicado") or E.siguiente_radicado(), key=f"{prefijo}rad"),
        "fecha_radicacion": c2.date_input("Fecha de radicación", date.fromisoformat(b["fecha_radicacion"])
                                          if b.get("fecha_radicacion") else date.today(), key=f"{prefijo}fr").isoformat(),
        "estado": c3.selectbox("Estado", E.estados(), index=E.estados().index(b.get("estado", "radicado")), key=f"{prefijo}est"),
    }
    c1, c2, c3 = st.columns(3)
    datos["solicitante"] = c1.text_input("Solicitante / titular", b.get("solicitante", ""), key=f"{prefijo}sol")
    datos["tipo_persona"] = c2.selectbox("Persona", ["natural", "juridica"],
                                         index=["natural", "juridica"].index(b.get("tipo_persona", "natural")), key=f"{prefijo}tp")
    datos["documento"] = c3.text_input("Cédula / NIT", b.get("documento") or "", key=f"{prefijo}doc")
    c1, c2, c3 = st.columns(3)
    datos["telefono"] = c1.text_input("Teléfono", b.get("telefono") or "", key=f"{prefijo}tel")
    datos["correo"] = c2.text_input("Correo", b.get("correo") or "", key=f"{prefijo}mail")
    datos["autoriza_notificacion_correo"] = int(c3.checkbox("Autoriza notificación por correo",
                                                            bool(b.get("autoriza_notificacion_correo")), key=f"{prefijo}aut"))
    st.markdown("**Predio**")
    c1, c2, c3 = st.columns(3)
    datos["direccion"] = c1.text_input("Dirección", b.get("direccion") or "", key=f"{prefijo}dir")
    datos["matricula"] = c2.text_input("Matrícula inmobiliaria", b.get("matricula") or "", placeholder="020-12345", key=f"{prefijo}mat")
    datos["cedula_catastral"] = c3.text_input("Cédula catastral", b.get("cedula_catastral") or "", key=f"{prefijo}cc")
    c1, c2, c3, c4 = st.columns(4)
    datos["clase_suelo"] = c1.selectbox("Clase de suelo", list(SUELOS), format_func=SUELOS.get,
                                        index=list(SUELOS).index(b.get("clase_suelo") or ""), key=f"{prefijo}cs")
    polis = [""] + [p["codigo"] for p in P.poligonos()]
    datos["poligono"] = c2.selectbox("Polígono (art. 138)", polis, index=polis.index(b.get("poligono") or "")
                                     if (b.get("poligono") or "") in polis else 0, key=f"{prefijo}pol")
    datos["area_actividad"] = c3.selectbox("Área de actividad", list(AREAS), format_func=AREAS.get,
                                           index=list(AREAS).index(b.get("area_actividad") or ""), key=f"{prefijo}aa")
    datos["estrato"] = c4.number_input("Estrato", 0, 6, int(b.get("estrato") or 0), key=f"{prefijo}estr") or None
    c1, c2 = st.columns(2)
    datos["responsable"] = c1.text_input("Funcionario responsable", b.get("responsable") or usuario().get("nombre", ""), key=f"{prefijo}resp")
    datos["observaciones"] = c2.text_area("Observaciones", b.get("observaciones") or "", key=f"{prefijo}obs", height=68)
    return datos


def _form_datos_tramite(prefijo: str, tipo: str, base: dict | None = None) -> dict:
    b = base or {}
    cat = E.tipos()[tipo]
    nombres = E.campos()
    visibles = list(dict.fromkeys(cat.get("campos", []) + ["area_otros_usos", "n_viviendas", "frente_lote", "seccion_via",
                                                            "area_excluida_ic", "fecha_cert_tradicion", "fecha_paz_salvo"]))
    datos = {}
    cols = st.columns(3)
    for i, c in enumerate(visibles):
        etiqueta = nombres.get(c, {}).get("etiqueta", c.replace("_", " ").capitalize())
        unidad = nombres.get(c, {}).get("unidad", "")
        obligatorio = " *" if c in cat.get("campos", []) else ""
        col = cols[i % 3]
        clave = f"{prefijo}{c}"
        if c.startswith("fecha"):
            v = col.text_input(f"{etiqueta}{obligatorio} (AAAA-MM-DD)", b.get(c, ""), key=clave)
        elif c == "categoria_rural":
            v = col.selectbox(f"{etiqueta}{obligatorio}", list(CATEGORIAS_RURALES), format_func=CATEGORIAS_RURALES.get,
                              index=list(CATEGORIAS_RURALES).index(b.get(c, "")), key=clave)
        elif c in ("uso_principal", "licencia_anterior"):
            v = col.text_input(f"{etiqueta}{obligatorio}", b.get(c, ""), key=clave,
                               help="Escriba 'residencial' o el código CIIU de 4 dígitos (ver Consulta → Usos)." if c == "uso_principal" else None)
        else:
            v = col.number_input(f"{etiqueta}{obligatorio} ({unidad})" if unidad else etiqueta + obligatorio,
                                 min_value=0.0, value=float(b.get(c) or 0), key=clave)
            v = v if v else None
        datos[c] = v if v not in ("",) else None
    return {k: v for k, v in datos.items() if v is not None}


def _verificacion(exp, tr):
    res = V.verificar(exp, tr)
    r = V.resumen(res)
    st.markdown(f"**Resultado general: {r['global']}** · " +
                " · ".join(f"{k}: {v}" for k, v in r.items() if k != "global"))
    df = pd.DataFrame(res).rename(columns={"item": "Ítem", "estado": "Estado", "detalle": "Detalle", "fuente": "Fuente"})
    st.dataframe(df.style.map(lambda v: f"background-color: {COLOR.get(v, '')}", subset=["Estado"]),
                 hide_index=True, use_container_width=True)


def _detalle(eid: int):
    exp = E.obtener(eid)
    if not exp:
        st.error("Expediente no encontrado.")
        return
    st.subheader(f"Expediente {exp['radicado']} — {exp['solicitante']}")
    t1, t5, t2, t3, t4 = st.tabs(["Trámites", "Documentos", "Datos del expediente", "Agregar trámite", "Historial"])
    with t5:
        from paginas import documentos_pag
        documentos_pag.panel_expediente(eid)

    with t1:
        trs = E.tramites(eid)
        if not trs:
            st.info("Este expediente no tiene trámites. Agréguelo en la pestaña 'Agregar trámite'.")
        for tr in trs:
            nombre = E.tipos()[tr["tipo"]]["nombre"]
            with st.expander(f"#{tr['id']} · {nombre} · {tr['modalidad'] or ''} · {tr['estado']} · vence {tr['fecha_limite']}",
                             expanded=len(trs) == 1):
                _verificacion(exp, tr)
                if puede("expedientes"):
                    st.markdown("**Editar**")
                    c1, c2 = st.columns(2)
                    mods = E.tipos()[tr["tipo"]]["modalidades"]
                    modalidad = c1.selectbox("Modalidad", mods, index=mods.index(tr["modalidad"]) if tr["modalidad"] in mods else 0,
                                             key=f"mod{tr['id']}")
                    estado = c2.selectbox("Estado", E.estados(), index=E.estados().index(tr["estado"]), key=f"est{tr['id']}")
                    datos = _form_datos_tramite(f"t{tr['id']}_", tr["tipo"], tr["datos"])
                    obs = st.text_area("Observaciones", tr["observaciones"] or "", key=f"obs{tr['id']}")
                    motivo = st.text_input("Motivo del cambio (opcional)", key=f"mot{tr['id']}")
                    if st.button("Guardar cambios del trámite", key=f"g{tr['id']}"):
                        E.editar_tramite(tr["id"], {"modalidad": modalidad, "estado": estado, "datos": datos,
                                                    "observaciones": obs}, usuario()["usuario"], motivo or None)
                        st.success("Trámite actualizado.")
                        st.rerun()
                    m = confirmar_eliminacion(f"tr{tr['id']}", f"el trámite #{tr['id']} ({nombre})")
                    if m:
                        E.eliminar_tramite(tr["id"], usuario()["usuario"], m)
                        st.success("Trámite eliminado. Quedó una copia completa en el historial y en Auditoría.")
                        st.rerun()

    with t2:
        if puede("expedientes"):
            datos = _form_expediente(f"e{eid}_", exp)
            motivo = st.text_input("Motivo del cambio (opcional)", key=f"me{eid}")
            if st.button("Guardar expediente"):
                try:
                    E.editar(eid, datos, usuario()["usuario"], motivo or None)
                    st.success("Expediente actualizado.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
            if puede("*"):
                m = confirmar_eliminacion(f"exp{eid}", "el expediente completo (incluye sus trámites)")
                if m:
                    E.eliminar_expediente(eid, usuario()["usuario"], m)
                    st.session_state.pop("expediente_abierto", None)
                    st.success("Expediente eliminado y registrado en auditoría.")
                    st.rerun()
        else:
            st.json(exp)

    with t3:
        if puede("expedientes"):
            tipos = E.tipos()
            tipo = st.selectbox("Tipo de trámite", list(tipos), format_func=lambda k: tipos[k]["nombre"], key="nuevo_tipo")
            st.caption(f"Fuente: {tipos[tipo]['fuente']}")
            c1, c2 = st.columns(2)
            modalidad = c1.selectbox("Modalidad", tipos[tipo]["modalidades"], key="nuevo_mod")
            fr = c2.date_input("Fecha de radicación del trámite", date.today(), key="nuevo_fr")
            datos = _form_datos_tramite("n_", tipo)
            obs = st.text_area("Observaciones", key="nuevo_obs")
            if st.button("Agregar trámite", type="primary"):
                E.agregar_tramite(eid, tipo, modalidad, datos, usuario()["usuario"], fr.isoformat(), obs)
                st.success("Trámite agregado. Revise la verificación en la pestaña Trámites.")
                st.rerun()

    with t4:
        h = E.historial(eid)
        st.dataframe(pd.DataFrame(h), hide_index=True, use_container_width=True) if h else st.info("Sin movimientos.")


def mostrar():
    st.title("Expedientes y trámites")
    venc = E.vencimientos(5)
    if venc:
        st.warning(f"{len(venc)} trámites vencen en 5 días hábiles o ya vencieron: " +
                   ", ".join(f"{v['radicado']} (#{v['id']}, {v['fecha_limite']})" for v in venc[:8]))

    vista = st.radio("Vista", ["Buscar", "Nuevo expediente"], horizontal=True,
                     index=0 if "expediente_abierto" in st.session_state or not puede("expedientes") else 0)
    if vista == "Nuevo expediente":
        if not puede("expedientes"):
            st.warning("Su rol no puede crear expedientes.")
            return
        with st.form("nuevo_expediente"):
            datos = _form_expediente("n_")
            if st.form_submit_button("Crear expediente", type="primary"):
                try:
                    eid = E.crear(datos, usuario()["usuario"])
                    st.session_state["expediente_abierto"] = eid
                    st.success(f"Expediente {datos['radicado']} creado. Agregue el trámite en la vista Buscar.")
                except Exception as e:
                    st.error(str(e))
        return

    c1, c2, c3 = st.columns([2, 1, 1])
    texto = c1.text_input("Buscar", placeholder="radicado, solicitante, matrícula, cédula catastral, dirección")
    estado = c2.selectbox("Estado", ["(todos)"] + E.estados())
    tipos = E.tipos()
    tipo = c3.selectbox("Tipo de trámite", ["(todos)"] + list(tipos), format_func=lambda k: tipos.get(k, {}).get("nombre", k))
    lista = E.listar(texto, None if estado.startswith("(") else estado, None if tipo.startswith("(") else tipo)
    if not lista:
        st.info("No hay expedientes con esos criterios.")
        return
    df = pd.DataFrame(lista)[["id", "radicado", "fecha_radicacion", "solicitante", "matricula", "direccion",
                              "clase_suelo", "poligono", "estado", "n_tramites", "responsable"]]
    st.dataframe(df, hide_index=True, use_container_width=True)
    ids = [x["id"] for x in lista]
    actual = st.session_state.get("expediente_abierto")
    eid = st.selectbox("Abrir expediente", ids, index=ids.index(actual) if actual in ids else 0,
                       format_func=lambda i: next(f"{x['radicado']} — {x['solicitante']}" for x in lista if x["id"] == i))
    st.session_state["expediente_abierto"] = eid
    _detalle(eid)
