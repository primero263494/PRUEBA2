"""Página: configuración (lectura de escaneos, conversión DWG, repositorio)."""
import streamlit as st

from core import ajustes, auditoria, conversores, lectura
from paginas.comun import usuario


def _guardar(ruta, valor):
    cambio = ajustes.fijar(ruta, valor)
    auditoria.registrar(usuario()["usuario"], "editar", "ajuste", ruta, despues={ruta: valor})
    return cambio


def mostrar():
    st.title("Configuración")
    a = ajustes.cargar()

    st.subheader("Lectura de escaneos")
    modos = {"auto": "Automático — IA si hay internet y clave; si no, OCR local",
             "local": "Solo local — OCR en el equipo, sin internet",
             "ia": "IA — modelo de visión por API (los archivos salen del equipo)"}
    actual = a["lectura_escaneos"]["modo"]
    modo = st.radio("Modo", list(modos), index=list(modos).index(actual), format_func=modos.get)
    ok, msg = lectura.ia_disponible()
    st.caption(("✅ " if ok else "⚠️ ") + msg)
    st.caption(f"La clave se lee de la variable de entorno {a['lectura_escaneos']['ia_variable_clave']}; "
               "nunca se guarda en archivos del programa.")
    modelo = st.text_input("Modelo de IA", a["lectura_escaneos"]["ia_modelo"])
    if st.button("Guardar lectura"):
        _guardar("lectura_escaneos.modo", modo)
        _guardar("lectura_escaneos.ia_modelo", modelo)
        st.success("Guardado.")

    st.subheader("Conversión de DWG a DXF")
    disp = conversores.disponibles()
    st.caption(f"ODA File Converter: {disp['oda'] or 'no encontrado'} · LibreDWG: {disp['libredwg'] or 'no encontrado'}")
    motores = {"auto": "Automático (ODA y luego LibreDWG)",
               "oda": "ODA File Converter (gratuito, propietario)",
               "libredwg": "LibreDWG (libre, GPL)"}
    motor = st.radio("Motor", list(motores), index=list(motores).index(a["conversion_dwg"]["motor"]),
                     format_func=motores.get)
    r_oda = st.text_input("Ruta de ODAFileConverter.exe", a["conversion_dwg"]["ruta_oda"])
    r_lib = st.text_input("Ruta de dwg2dxf.exe", a["conversion_dwg"]["ruta_libredwg"])
    if st.button("Guardar conversión"):
        _guardar("conversion_dwg.motor", motor)
        _guardar("conversion_dwg.ruta_oda", r_oda)
        _guardar("conversion_dwg.ruta_libredwg", r_lib)
        st.success("Guardado.")

    st.subheader("Repositorio en línea")
    url = st.text_input("URL del repositorio (GitHub u otro)", a["repositorio"]["url"])
    st.caption("El código y los parámetros se versionan en el repositorio. La base de datos, los expedientes "
               "y las normas cargadas NO se suben (contienen datos personales); respáldelos aparte.")
    if st.button("Guardar repositorio"):
        _guardar("repositorio.url", url)
        st.success("Guardado.")
