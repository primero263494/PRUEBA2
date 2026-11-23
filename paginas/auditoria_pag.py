"""Página: registro de auditoría (quién cambió qué, cuándo y por qué)."""
import pandas as pd
import streamlit as st

from core import auditoria


def mostrar():
    st.title("Auditoría")
    c1, c2 = st.columns(2)
    entidad = c1.selectbox("Entidad", ["(todas)", "expediente", "tramite", "documento", "parametro", "norma", "capa", "usuario", "ajuste", "sesion"])
    usuario = c2.text_input("Usuario")
    filas = auditoria.listar(entidad=None if entidad.startswith("(") else entidad, usuario=usuario or None)
    df = pd.DataFrame(filas)
    st.dataframe(df, use_container_width=True, hide_index=True)
    if not df.empty:
        st.download_button("Descargar CSV", df.to_csv(index=False).encode("utf-8-sig"),
                           "auditoria.csv", "text/csv")
