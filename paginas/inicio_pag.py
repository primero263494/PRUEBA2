"""Página de inicio: estado del sistema y pendientes."""
import streamlit as st

from core import cartografia, lectura, normas
from core import parametros as P
from paginas.comun import usuario


def mostrar():
    st.title("Trámites urbanísticos · El Carmen de Viboral")
    st.write(f"Bienvenido(a), {usuario().get('nombre', '')}.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Parámetros pendientes", len(P.pendientes()))
    c2.metric("Tarifas con nota", len(P.alertas_tarifas()))
    c3.metric("Normas cargadas", len(normas.listar()))
    c4.metric("Capas cargadas", len(cartografia.listar()))

    modo, explicacion = lectura.modo_efectivo()
    st.caption(f"Lectura de escaneos: {modo}. {explicacion}")

    sismo = P.obtener("nsr10.amenaza_sismica_municipio.Aa")
    st.info(f"Amenaza sísmica del municipio: Aa = {P.valor('nsr10.amenaza_sismica_municipio.Aa')}, "
            f"Av = {P.valor('nsr10.amenaza_sismica_municipio.Av')}, zona "
            f"{P.valor('nsr10.amenaza_sismica_municipio.zona_amenaza')} ({sismo.fuente}).")

    if not normas.listar():
        st.info("Para buscar en los textos de la norma: Normas → Cargar → **Cargar normas base**.")
    faltan = cartografia.roles_faltantes()
    if faltan:
        st.warning("Cartografía por cargar: " + ", ".join(cartografia.ROLES[r][0] for r in faltan) +
                   ". Vaya a Cartografía → Cargar capa.")
    st.markdown(
        "**Módulos disponibles:** expedientes y trámites (con verificación contra la norma), gestión documental (carga, vista previa, documentos exigidos), consulta normativa (buscador, fichas por zona, usos del suelo, cesiones), "
        "parámetros normativos, normas y normograma, cartografía y cruce del predio, configuración, usuarios y "
        "auditoría. **En desarrollo:** "
        "listas de chequeo, calculadoras, análisis de planos e informes."
    )
