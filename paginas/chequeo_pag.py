"""Página: listas de chequeo (módulo 5)."""
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from core import chequeo as C, db, expedientes as E
from core import parametros as P
from paginas.comun import puede, usuario


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
        resumen.append({"Trámite": f["id"], "Radicado": f["radicado"], "Solicitante": f["solicitante"],
                        "Tipo": E.tipos()[f["tipo"]]["nombre"], "Estado": f["estado"], "Vence": f["fecha_limite"],
                        "Avance": f"{a['avance']:.0%}", "No cumple": a["no_cumple"], "Pendientes": a["pendiente"]})
    st.dataframe(pd.DataFrame(resumen), hide_index=True, use_container_width=True)
    tid = st.selectbox("Abrir lista", [f["id"] for f in filas],
                       format_func=lambda i: next(f"#{x['id']} · {x['radicado']} · {E.tipos()[x['tipo']]['nombre']}"
                                                  for x in filas if x["id"] == i))
    panel_tramite(tid)
