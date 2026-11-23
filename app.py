"""Gestión y revisión de trámites urbanísticos — El Carmen de Viboral.

Ejecutar:  streamlit run app.py   (o doble clic en iniciar.bat)
"""
import streamlit as st

from core import auth, db

st.set_page_config(page_title="Trámites urbanísticos · El Carmen de Viboral",
                   page_icon="🏛️", layout="wide")

db.migrar()

from paginas import (auditoria_pag, cartografia_pag, configuracion_pag, inicio_pag,  # noqa: E402
                     normas_pag, parametros_pag, planos_pag, usuarios_pag)

PAGINAS = [
    # (título, función, permiso requerido)
    ("Inicio", inicio_pag.mostrar, None),
    ("Parámetros normativos", parametros_pag.mostrar, "ver_parametros"),
    ("Normas cargadas", normas_pag.mostrar, "ver_norma"),
    ("Cartografía", cartografia_pag.mostrar, "ver_cartografia"),
    ("Análisis de planos", planos_pag.mostrar, "analizar_planos"),
    ("Configuración", configuracion_pag.mostrar, "*"),
    ("Usuarios", usuarios_pag.mostrar, "*"),
    ("Auditoría", auditoria_pag.mostrar, "*"),
]


def pantalla_primer_administrador():
    st.title("Configuración inicial")
    st.info("No hay usuarios. Cree la cuenta del administrador.")
    with st.form("primer_admin"):
        usuario = st.text_input("Usuario")
        nombre = st.text_input("Nombre completo")
        c1 = st.text_input("Contraseña (mínimo 8 caracteres)", type="password")
        c2 = st.text_input("Repita la contraseña", type="password")
        if st.form_submit_button("Crear administrador"):
            if c1 != c2:
                st.error("Las contraseñas no coinciden.")
            else:
                try:
                    auth.crear_usuario(usuario, nombre, "administrador", c1, creado_por="sistema")
                    st.success("Administrador creado. Ingrese con sus datos.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))


def pantalla_ingreso():
    st.title("Trámites urbanísticos")
    st.caption("Secretaría de Planeación · El Carmen de Viboral")
    with st.form("ingreso"):
        u = st.text_input("Usuario")
        c = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Ingresar"):
            datos = auth.verificar(u, c)
            if datos:
                st.session_state["usuario"] = datos
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")


def main():
    if not auth.hay_usuarios():
        pantalla_primer_administrador()
        return
    if "usuario" not in st.session_state:
        pantalla_ingreso()
        return

    u = st.session_state["usuario"]
    visibles = [p for p in PAGINAS if p[2] is None or auth.puede(u["rol"], p[2])]
    with st.sidebar:
        st.markdown(f"**{u['nombre']}**  \n{u['rol'].capitalize()}")
        eleccion = st.radio("Menú", [p[0] for p in visibles], label_visibility="collapsed")
        if st.button("Salir"):
            st.session_state.clear()
            st.rerun()
    dict((p[0], p[1]) for p in visibles)[eleccion]()


main()
