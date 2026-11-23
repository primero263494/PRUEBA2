"""Página: listas de chequeo (módulo 5)."""
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from core import chequeo as C, db, expedientes as E
from core import parametros as P
from paginas.comun import campo_fecha, guardar_subidos, puede, usuario


def _panel_paquete(tramite_id: int, editable: bool):
    """Marca de 'paquete completo para revisión'."""
    pq = C.paquete(tramite_id)
    pend = pq["pendientes"]
    if pq["completo"]:
        st.success(f"📦 Paquete COMPLETO para revisión desde el {pq['fecha_completo']} (marcado por {pq['usuario']})."
                   + (f" Observación: {pq['observacion']}" if pq["observacion"] else ""))
    elif pend:
        st.warning(f"📦 Paquete INCOMPLETO: faltan {len(pend)} documentos obligatorios por marcar como cumple.")
    else:
        st.info("📦 Todos los documentos obligatorios están en cumple o no aplica: puede marcar el paquete como completo.")
    if not editable:
        return
    with st.expander("Marcar paquete completo para revisión" if not pq["completo"] else "Reabrir paquete"):
        if not pq["completo"]:
            c1, c2 = st.columns([1, 2])
            fecha = campo_fecha(c1, "Fecha en que quedó completo", None, key=f"pqf{tramite_id}", obligatorio=True)
            obs = c2.text_input("Observación", key=f"pqo{tramite_id}")
            forzar = bool(pend) and st.checkbox("Marcar completo aunque falten documentos (exige observación)",
                                                key=f"pqx{tramite_id}")
            if pend:
                st.caption("Pendientes: " + "; ".join(i["texto"].split(" — ")[0].replace("Documento: ", "") for i in pend))
            if st.button("Marcar paquete completo", type="primary", key=f"pqb{tramite_id}", disabled=bool(pend) and not forzar):
                try:
                    C.marcar_paquete(tramite_id, True, usuario()["usuario"], fecha, obs, forzar=forzar)
                    st.success("Paquete marcado completo. El trámite pasa a 'en revisión' si estaba radicado.")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        else:
            obs = st.text_input("Motivo para reabrir", key=f"pqr{tramite_id}")
            if st.button("Reabrir paquete", key=f"pqrb{tramite_id}") and obs.strip():
                C.marcar_paquete(tramite_id, False, usuario()["usuario"], observacion=obs)
                st.rerun()


def _seccion_documentos(tramite_id: int, filas: list, sug: dict, editable: bool):
    """Documentos: cumple / no cumple / no aplica con observación y, al lado, subir el archivo."""
    from core import documentos as D
    cat = D.catalogo()
    a_clave = {v: k for k, v in C.ETIQUETAS.items()}
    etiquetas = list(C.ETIQUETAS.values())
    cambios = {}
    for i in filas:
        opciones = i["item_id"][4:].split("|")
        c1, c2, c3, c4 = st.columns([5, 2, 4, 1.4])
        icono = {"cumple": "✅", "no_cumple": "❌", "no_aplica": "➖", "pendiente": "⏳"}[i["estado"]]
        c1.markdown(f"{icono} {i['texto']}")
        if i["item_id"] in sug and i["estado"] == "pendiente":
            c1.caption(f"Sugerencia: {C.ETIQUETAS[sug[i['item_id']][0]]} ({sug[i['item_id']][1]})")
        est = c2.selectbox("Estado", etiquetas, index=etiquetas.index(C.ETIQUETAS[i["estado"]]), key=f"de{i['id']}",
                           label_visibility="collapsed", disabled=not editable)
        obs = c3.text_input("Observación", i["observacion"] or "", key=f"do{i['id']}", label_visibility="collapsed",
                            placeholder="Observación", disabled=not editable)
        cambios[i["id"]] = (a_clave[est], obs, i)
        if editable:
            with c4.popover("📎 Subir"):
                tipo = opciones[0] if len(opciones) == 1 else st.selectbox(
                    "Documento", opciones, format_func=lambda o: cat[o]["nombre"], key=f"dt{i['id']}")
                arch = st.file_uploader("Archivo", key=f"df{i['id']}")
                fecha = campo_fecha(st, "Fecha de expedición" + (" (obligatoria: vigencia 1 mes)" if cat[tipo].get("vigencia_dias") else ""),
                                    None, key=f"dfe{i['id']}")
                if st.button("Cargar", key=f"dfb{i['id']}", disabled=arch is None):
                    try:
                        r = C.subir_documento_item(i["id"], guardar_subidos([arch])[0], usuario()["usuario"], fecha,
                                                   nombre_original=arch.name, tipo_documento=tipo)
                        st.success(f"Cargado (versión {r['version']}). Ítem: {C.ETIQUETAS[r['estado']]}.")
                        st.rerun()
                    except (ValueError, KeyError) as e:
                        st.error(str(e))
    if editable and st.button("Guardar documentos", key=f"gsdoc{tramite_id}"):
        errores = 0
        for pk, (estado, obs, orig) in cambios.items():
            if estado != orig["estado"] or (obs or "") != (orig["observacion"] or ""):
                try:
                    C.marcar(pk, estado, obs, usuario()["usuario"])
                except ValueError as e:
                    errores += 1
                    st.error(f"{orig['texto'][:60]}…: {e}")
        if not errores:
            st.success("Documentos guardados.")
            st.rerun()


def panel_tramite(tramite_id: int):
    nuevos = C.generar(tramite_id)
    if nuevos:
        st.caption(f"Se agregaron {nuevos} ítems a la lista.")
    a = C.avance(tramite_id)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Avance", f"{a['avance']:.0%}")
    c2.metric("Cumple", a["cumple"])
    c3.metric("No cumple", a["no_cumple"])
    c4.metric("No aplica", a["no_aplica"])
    c5.metric("Pendientes", a["pendiente"])
    st.progress(a["avance"])

    editable = puede("expedientes")
    _panel_paquete(tramite_id, editable)
    sug = C.sugerencias(tramite_id)
    if editable and sug:
        c1, c2 = st.columns([3, 1])
        c1.caption(f"El programa tiene {len(sug)} sugerencias a partir de la verificación y los documentos cargados. "
                   "Revise antes de aplicar: usted confirma cada estado.")
        if c2.button("Aplicar sugerencias a pendientes", key=f"sug{tramite_id}"):
            n = C.aplicar_sugerencias(tramite_id, usuario()["usuario"])
            st.success(f"{n} ítems marcados con la sugerencia.")
            st.rerun()

    secciones = P.valor("listas.secciones")
    lista = C.items(tramite_id)
    etiquetas = list(C.ETIQUETAS.values())
    a_clave = {v: k for k, v in C.ETIQUETAS.items()}
    for sec in dict.fromkeys(i["seccion"] for i in lista):
        filas = [i for i in lista if i["seccion"] == sec]
        hechos = sum(1 for i in filas if i["estado"] != "pendiente")
        with st.expander(f"{secciones.get(sec, {}).get('nombre', sec)} — {hechos}/{len(filas)}",
                         expanded=any(i["estado"] in ("pendiente", "no_cumple") for i in filas)):
            if sec == "documentos":
                _seccion_documentos(tramite_id, filas, sug, editable)
                continue
            df = pd.DataFrame([{"id": i["id"], "Ítem": i["texto"], "Estado": C.ETIQUETAS[i["estado"]],
                                "Observación": i["observacion"] or "",
                                "Sugerencia": C.ETIQUETAS[sug[i["item_id"]][0]] if i["item_id"] in sug else "",
                                "Fuente": i["fuente"] or ""} for i in filas])
            ed = st.data_editor(
                df, hide_index=True, use_container_width=True, key=f"ed{tramite_id}{sec}",
                disabled=not editable,
                column_config={
                    "id": None,
                    "Ítem": st.column_config.TextColumn(disabled=True, width="large"),
                    "Estado": st.column_config.SelectboxColumn(options=etiquetas, required=True),
                    "Observación": st.column_config.TextColumn(width="medium"),
                    "Sugerencia": st.column_config.TextColumn(disabled=True),
                    "Fuente": st.column_config.TextColumn(disabled=True),
                })
            if editable and st.button("Guardar sección", key=f"gs{tramite_id}{sec}"):
                errores = 0
                for _, f in ed.iterrows():
                    orig = next(i for i in filas if i["id"] == f["id"])
                    estado = a_clave[f["Estado"]]
                    if estado != orig["estado"] or (f["Observación"] or "") != (orig["observacion"] or ""):
                        try:
                            C.marcar(int(f["id"]), estado, f["Observación"], usuario()["usuario"])
                        except ValueError as e:
                            errores += 1
                            st.error(f"{f['Ítem'][:60]}…: {e}")
                if not errores:
                    st.success("Sección guardada.")
                    st.rerun()

    if a["pendientes"]:
        with st.expander(f"Pendientes y no cumple ({len(a['pendientes'])})"):
            for i in a["pendientes"]:
                st.markdown(f"- **{C.ETIQUETAS[i['estado']]}** — {i['texto']}"
                            + (f"  \n  _{i['observacion']}_" if i["observacion"] else ""))
    ruta = Path(tempfile.mkdtemp()) / f"lista_chequeo_tramite_{tramite_id}.xlsx"
    C.exportar_excel(tramite_id, ruta)
    st.download_button("Descargar lista en Excel", ruta.read_bytes(), file_name=ruta.name,
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"xl{tramite_id}")


def panel_expediente(eid: int):
    trs = E.tramites(eid)
    if not trs:
        st.info("Agregue un trámite para generar su lista de chequeo.")
        return
    nombres = {t["id"]: f"#{t['id']} {E.tipos()[t['tipo']]['nombre']}" for t in trs}
    tid = st.selectbox("Trámite", list(nombres), format_func=nombres.get, key=f"chk_tr{eid}")
    panel_tramite(tid)


def mostrar():
    st.title("Listas de chequeo")
    filas = db.consultar(
        "SELECT t.id, t.tipo, t.estado, t.fecha_limite, e.radicado, e.solicitante, e.id AS eid "
        "FROM tramites t JOIN expedientes e ON e.id=t.expediente_id ORDER BY t.id DESC LIMIT 300")
    if not filas:
        st.info("No hay trámites. Cree un expediente y agregue un trámite.")
        return
    resumen = []
    for f in filas:
        C.generar(f["id"])
        a = C.avance(f["id"])
        pq = db.consultar("SELECT completo, fecha_completo FROM chequeo_paquete WHERE tramite_id=?", (f["id"],))
        resumen.append({"Paquete": f"Completo {pq[0]['fecha_completo']}" if pq and pq[0]["completo"] else "Incompleto","Trámite": f["id"], "Radicado": f["radicado"], "Solicitante": f["solicitante"],
                        "Tipo": E.tipos()[f["tipo"]]["nombre"], "Estado": f["estado"], "Vence": f["fecha_limite"],
                        "Avance": f"{a['avance']:.0%}", "No cumple": a["no_cumple"], "Pendientes": a["pendiente"]})
    st.dataframe(pd.DataFrame(resumen), hide_index=True, use_container_width=True)
    tid = st.selectbox("Abrir lista", [f["id"] for f in filas],
                       format_func=lambda i: next(f"#{x['id']} · {x['radicado']} · {E.tipos()[x['tipo']]['nombre']}"
                                                  for x in filas if x["id"] == i))
    panel_tramite(tid)
