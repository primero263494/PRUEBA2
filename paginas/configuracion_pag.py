"""Página: configuración (lectura de escaneos, conversión DWG, repositorio)."""
import streamlit as st

from core import ajustes, auditoria, conversores, lectura, respaldo
from paginas.comun import usuario


def _guardar(ruta, valor):
    cambio = ajustes.fijar(ruta, valor)
    auditoria.registrar(usuario()["usuario"], "editar", "ajuste", ruta, despues={ruta: valor})
    return cambio


def _respaldo():
    st.subheader("Respaldo de los datos")
    if respaldo.en_la_nube():
        st.warning("El programa está en Streamlit Cloud: cuando el servidor se reinicia (actualización, inactividad o "
                   "falla) se borran la base de datos y los archivos subidos. Descargue un respaldo al terminar cada "
                   "jornada y restáurelo si encuentra el programa vacío.")
    st.caption("El respaldo es un .zip con la base (expedientes, usuarios, auditoría, cálculos, informes) y los archivos "
               "subidos. Último respaldo: " + (respaldo.ultimo() or "ninguno") + ".")
    if st.button("Preparar respaldo"):
        contenido, nombre = respaldo.crear()
        st.session_state["respaldo_listo"] = (contenido, nombre)
        auditoria.registrar(usuario()["usuario"], "crear", "respaldo", nombre)
    if st.session_state.get("respaldo_listo"):
        contenido, nombre = st.session_state["respaldo_listo"]
        st.download_button(f"Descargar {nombre} ({len(contenido) / 1e6:.1f} MB)", contenido, nombre, "application/zip",
                           type="primary")
    with st.expander("Restaurar un respaldo (reemplaza todos los datos actuales)"):
        arch = st.file_uploader("Respaldo .zip", type=["zip"], key="restaurar_conf")
        if arch is not None:
            try:
                info = respaldo.validar(arch.getvalue())
                st.write(f"Respaldo del {info['fecha']} con {info['archivos']} archivos.")
                confirma = st.text_input("Escriba RESTAURAR para confirmar")
                if st.button("Restaurar", type="primary", disabled=confirma.strip().upper() != "RESTAURAR"):
                    respaldo.restaurar(arch.getvalue())
                    st.session_state.clear()
                    st.query_params.clear()
                    st.rerun()
            except Exception as e:
                st.error(str(e))
    st.divider()


def mostrar():
    st.title("Configuración")
    _respaldo()
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
    plantilla_informes()


def plantilla_informes():
    """Editor de la plantilla institucional (logo, encabezado, pie y firmas)."""
    import pandas as pd

    from core import informes
    from paginas.comun import guardar_subidos
    st.subheader("Plantilla de informes")
    pl = informes.plantilla()
    logo = informes._ruta_logo(pl)
    if logo:
        st.image(str(logo), width=160)
    else:
        st.caption("Sin logo: los informes muestran [LOGO].")
    sub = st.file_uploader("Logo (PNG o JPG)", type=["png", "jpg", "jpeg"])
    if sub and st.button("Guardar logo"):
        informes.guardar_logo(guardar_subidos([sub])[0], usuario()["usuario"])
        st.success("Logo guardado.")
        st.rerun()
    c1, c2 = st.columns(2)
    campos = {}
    for i, (k, et) in enumerate([("entidad", "Entidad"), ("dependencia", "Dependencia"), ("nit", "NIT"),
                                 ("direccion", "Dirección"), ("telefono", "Teléfono"), ("correo", "Correo"),
                                 ("codigo_formato", "Código del formato"), ("version_formato", "Versión")]):
        campos[k] = (c1 if i % 2 == 0 else c2).text_input(et, str(pl.get(k, "")))
    campos["pie"] = st.text_area("Pie de página", pl.get("pie", ""))
    st.markdown("**Firmas** (agregue o quite filas)")
    firmas = st.data_editor(pd.DataFrame(pl.get("firmas", []), columns=["nombre", "cargo", "matricula"]),
                            num_rows="dynamic", hide_index=True, use_container_width=True)
    if st.button("Guardar plantilla"):
        datos = {**pl, **campos,
                 "firmas": [{k: ("" if pd.isna(v) else str(v)) for k, v in f.items()} for f in firmas.to_dict("records")
                            if str(f.get("nombre") or "").strip()]}
        informes.guardar_plantilla(datos, usuario()["usuario"])
        st.success("Plantilla guardada.")
