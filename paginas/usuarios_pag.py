"""Página: administración de usuarios y roles."""
import pandas as pd
import streamlit as st

from core import auth
from paginas.comun import usuario


def mostrar():
    st.title("Usuarios")
    lista = auth.listar()
    st.dataframe(pd.DataFrame(lista), use_container_width=True, hide_index=True)

    with st.expander("Crear usuario"):
        with st.form("nuevo_usuario", clear_on_submit=True):
            u = st.text_input("Usuario")
            n = st.text_input("Nombre completo")
            r = st.selectbox("Rol", auth.ROLES)
            c = st.text_input("Contraseña inicial (mínimo 8)", type="password")
            if st.form_submit_button("Crear"):
                try:
                    auth.crear_usuario(u, n, r, c, usuario()["usuario"])
                    st.success("Usuario creado.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    if lista:
        with st.expander("Cambiar rol o estado"):
            uid = st.selectbox("Usuario", [x["id"] for x in lista],
                               format_func=lambda i: next(x["usuario"] for x in lista if x["id"] == i))
            fila = next(x for x in lista if x["id"] == uid)
            rol = st.selectbox("Rol", auth.ROLES, index=auth.ROLES.index(fila["rol"]))
            activo = st.checkbox("Activo", value=bool(fila["activo"]))
            if st.button("Guardar cambios"):
                if fila["usuario"] == usuario()["usuario"] and (rol != "administrador" or not activo):
                    st.error("No puede quitarse a sí mismo el rol de administrador ni desactivarse.")
                else:
                    if rol != fila["rol"]:
                        auth.cambiar_rol(uid, rol, usuario()["usuario"])
                    if activo != bool(fila["activo"]):
                        auth.cambiar_estado(uid, activo, usuario()["usuario"])
                    st.success("Actualizado.")
                    st.rerun()
