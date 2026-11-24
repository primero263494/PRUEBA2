"""Página: informes (módulo 7) — informe técnico de revisión y acta de
observaciones en Word editable y PDF, con la plantilla institucional."""
from pathlib import Path

import pandas as pd
import streamlit as st

from core import db, expedientes as E, informes as I
from paginas.comun import indice_foco, puede, usuario

TIPOS = {"informe_tecnico": "Informe técnico de revisión", "acta_observaciones": "Acta de observaciones y correcciones"}


def _descargas(docx_r, pdf_r, clave):
    c1, c2 = st.columns(2)
    if docx_r and Path(docx_r).exists():
        c1.download_button("Descargar Word (.docx)", Path(docx_r).read_bytes(), Path(docx_r).name,
                           "application/vnd.openxmlformats-officedocument.wordprocessingml.document", key=f"w{clave}")
    if pdf_r and Path(pdf_r).exists():
        c2.download_button("Descargar PDF", Path(pdf_r).read_bytes(), Path(pdf_r).name, "application/pdf", key=f"p{clave}")


def panel_tramite(tramite_id: int):
    pl = I.plantilla()
    if not pl.get("logo") or any("[" in str(v) for v in (pl.get("nit"), pl.get("direccion"))):
        st.warning("La plantilla institucional tiene datos por completar (logo, dirección, firmas). "
                   "Un administrador los edita en Configuración → Plantilla de informes.")
    tipo = st.radio("Documento", list(TIPOS), format_func=TIPOS.get, horizontal=True, key=f"tipo_inf{tramite_id}")
    previo = I.contenido_acta(tramite_id) if tipo == "acta_observaciones" else I.contenido_informe(tramite_id)
    with st.expander("Vista previa del contenido", expanded=False):
        for bl in previo["bloques"]:
            if bl[0] in ("titulo", "subtitulo"):
                st.markdown(f"**{bl[1]}**")
            elif bl[0] in ("parrafo", "nota"):
                st.write(bl[1])
            elif bl[0] == "lista":
                st.markdown("\n".join(f"- {x}" for x in bl[1]))
            elif bl[0] == "tabla":
                st.dataframe(pd.DataFrame(bl[2], columns=bl[1]), hide_index=True, use_container_width=True)
    st.caption(f"Observaciones encontradas: {len(previo['observaciones'])}")
    conclusion = ""
    if tipo == "informe_tecnico":
        conclusion = st.text_area("Conclusión (puede editarla)", previo["conclusion_sugerida"], key=f"conc{tramite_id}")
    extra = st.text_area("Observaciones adicionales del revisor (una por línea)", key=f"extra{tramite_id}")
    desde_word = st.checkbox("Generar el PDF desde el Word con LibreOffice (si está instalado)", key=f"lo{tramite_id}")
    if puede("informes") and st.button("Generar documento", type="primary", key=f"gen{tramite_id}"):
        with st.spinner("Generando…"):
            r = I.generar(tramite_id, tipo, usuario()["usuario"], conclusion, extra, desde_word)
        st.success("Documento generado y guardado en la carpeta del trámite.")
        _descargas(r["docx"], r["pdf"], f"nuevo{tramite_id}")
    hist = I.listar(tramite_id)
    if hist:
        st.markdown("**Documentos generados**")
        for h in hist:
            st.caption(f"{h['fecha']} · {TIPOS.get(h['tipo'], h['tipo'])} · {h['usuario']}")
            _descargas(h["archivo_docx"], h["archivo_pdf"], h["id"])


def panel_expediente(eid: int):
    trs = E.tramites(eid)
    if not trs:
        st.info("El expediente no tiene trámites.")
        return
    op = {t["id"]: f"#{t['id']} · {E.tipos()[t['tipo']]['nombre']}" for t in trs}
    tid = st.selectbox("Trámite", list(op), format_func=op.get, key=f"inf_tr{eid}")
    panel_tramite(tid)


def mostrar():
    st.title("Informes")
    st.caption("Informe técnico de revisión (datos, verificación normativa, cálculos, lista de chequeo, análisis de planos, "
               "observaciones y conclusión) y acta de observaciones (Decreto 1077 de 2015, art. 2.2.6.1.2.2.4). "
               "Salen en Word editable y en PDF con la plantilla institucional.")
    filas = db.consultar("SELECT t.id, t.tipo, e.radicado, e.solicitante FROM tramites t JOIN expedientes e "
                         "ON e.id=t.expediente_id ORDER BY t.id DESC LIMIT 300")
    if not filas:
        st.info("Aún no hay trámites.")
        return
    op = {f["id"]: f"#{f['id']} · {f['radicado']} · {f['solicitante']} · {E.tipos()[f['tipo']]['nombre']}" for f in filas}
    panel_tramite(st.selectbox("Trámite", list(op), format_func=op.get, index=indice_foco(list(op))))
