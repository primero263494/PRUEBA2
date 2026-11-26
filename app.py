"""Gestión y revisión de trámites urbanísticos — El Carmen de Viboral.

Ejecutar:  streamlit run app.py   (o doble clic en iniciar.bat)
"""
import streamlit as st

from core import auth, borradores, calculadoras, chequeo, db, documentos, expedientes, informes, respaldo, sesiones
from core.planos import analisis as analisis_planos

st.set_page_config(page_title="Trámites urbanísticos · El Carmen de Viboral",
                   page_icon="🏛️", layout="wide")

db.migrar()
expedientes.migrar()
documentos.migrar()
chequeo.migrar()
calculadoras.migrar()
analisis_planos.migrar()
informes.migrar()
sesiones.migrar()
borradores.migrar()

from paginas import (auditoria_pag, informes_pag, calculadoras_pag, cartografia_pag, chequeo_pag, configuracion_pag, consulta_pag,  # noqa: E402
                     documentos_pag, expedientes_pag, inicio_pag, normas_pag, parametros_pag, planos_pag, usuarios_pag)

PAGINAS = [
    # (título, función, permiso requerido)
    ("Inicio", inicio_pag.mostrar, None),
    ("Expedientes y trámites", expedientes_pag.mostrar, "ver_norma"),
    ("Gestión documental", documentos_pag.mostrar, "expedientes"),
    ("Listas de chequeo", chequeo_pag.mostrar, "expedientes"),
    ("Calculadoras", calculadoras_pag.mostrar, "ver_norma"),
    ("Consulta normativa", consulta_pag.mostrar, "ver_norma"),
    ("Parámetros normativos", parametros_pag.mostrar, "ver_parametros"),
    ("Normas cargadas", normas_pag.mostrar, "ver_norma"),
    ("Cartografía", cartografia_pag.mostrar, "ver_cartografia"),
    ("Análisis de planos", planos_pag.mostrar, "analizar_planos"),
    ("Informes", informes_pag.mostrar, "informes"),
    ("Configuración", configuracion_pag.mostrar, "*"),
    ("Usuarios", usuarios_pag.mostrar, "*"),
    ("Auditoría", auditoria_pag.mostrar, "*"),
]


def _restaurar_respaldo(clave: str):
    """Subir un respaldo .zip y reemplazar los datos actuales."""
    arch = st.file_uploader("Respaldo (.zip descargado desde Configuración → Respaldo)", type=["zip"], key=clave)
    if arch is not None:
        try:
            info = respaldo.validar(arch.getvalue())
            st.write(f"Respaldo del {info['fecha']} con {info['archivos']} archivos.")
            if st.button("Restaurar este respaldo", type="primary", key=clave + "_b"):
                respaldo.restaurar(arch.getvalue())
                st.session_state.clear()
                st.query_params.clear()
                st.success("Datos restaurados. Ingrese con su usuario.")
                st.rerun()
        except Exception as e:
            st.error(str(e))


def pantalla_primer_administrador():
    st.title("Configuración inicial")
    st.warning(f"La base de datos está vacía (creada el {sesiones.base_creada()}). Si ya había trabajado en el programa, "
               "el servidor se reinició y borró los datos: es lo que pasa en Streamlit Cloud, cuyo disco no es "
               "permanente. Restaure su último respaldo o, si es la primera vez, cree el administrador.")
    with st.expander("Restaurar un respaldo", expanded=True):
        _restaurar_respaldo("restaurar_inicial")
    st.info("Primera vez: cree la cuenta del administrador.")
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
                st.query_params["s"] = sesiones.crear(datos["id"])
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")


def main():
    if not auth.hay_usuarios():
        pantalla_primer_administrador()
        return
    if "usuario" not in st.session_state:
        # reconexión: la pestaña perdió su memoria pero la dirección conserva el código de sesión
        recuperado = sesiones.validar(st.query_params.get("s"))
        if recuperado:
            st.session_state["usuario"] = recuperado
        else:
            st.query_params.clear()
            pantalla_ingreso()
            return

    u = st.session_state["usuario"]
    visibles = [p for p in PAGINAS if p[2] is None or auth.puede(u["rol"], p[2])]
    titulos = [p[0] for p in visibles]
    if st.session_state.get("pagina") not in titulos:
        st.session_state["pagina"] = "Inicio"
    with st.sidebar:
        st.markdown(f"**{u['nombre']}**  \n{u['rol'].capitalize()}")
        st.button("⌂ Inicio", use_container_width=True, on_click=inicio_pag.ir_a, args=("Inicio",))
        eleccion = st.radio("Menú", titulos, key="pagina", label_visibility="collapsed")
        if st.button("Salir"):
            sesiones.cerrar(st.query_params.get("s"))
            st.query_params.clear()
            st.session_state.clear()
            st.rerun()
    dict((p[0], p[1]) for p in visibles)[eleccion]()


main()
