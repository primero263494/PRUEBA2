"""Página: cargar la cartografía del PBOT y Cornare por rol, y cruzar un predio."""
import pandas as pd
import streamlit as st

from core import cartografia as C
from paginas.comun import confirmar_eliminacion, exigir, guardar_subidos, puede, usuario

FORMATOS = ["zip", "shp", "shx", "dbf", "prj", "cpg", "geojson", "json", "kml", "kmz", "gpkg",
            "tif", "tiff", "pdf", "png", "jpg", "jpeg"]


def _estado():
    faltan = C.roles_faltantes()
    if faltan:
        st.warning("Para el cruce completo faltan capas con estos roles: " +
                   ", ".join(C.ROLES[r][0] for r in faltan) +
                   ". El análisis funciona con lo que esté cargado y avisa lo que no pudo revisar.")
    else:
        st.success("Están cargadas las capas mínimas para el cruce normativo.")


def _cargar():
    st.subheader("Cargar capa")
    st.caption("Shapefile: suba juntos .shp, .shx, .dbf y .prj, o un .zip. El sistema de coordenadas es "
               "obligatorio; el cruce se hace en MAGNA-SIRGAS / Origen Nacional (EPSG:9377).")
    with st.form("cargar_capa", clear_on_submit=True):
        archivos = st.file_uploader("Archivos de la capa", type=FORMATOS, accept_multiple_files=True)
        nombre = st.text_input("Nombre", placeholder="Tratamientos urbanos PBOT 2017")
        rol = st.selectbox("Rol de la capa", list(C.ROLES),
                           format_func=lambda r: f"{C.ROLES[r][0]}  ({C.ROLES[r][1]})" if C.ROLES[r][1] else C.ROLES[r][0])
        c1, c2 = st.columns(2)
        fuente = c1.text_input("Fuente", placeholder="Plano CG_007, PBOT 2017")
        campo = c2.text_input("Campo que identifica la zona (opcional)", placeholder="CODIGO, AMENAZA…")
        if st.form_submit_button("Cargar") and archivos and nombre:
            rutas = guardar_subidos(archivos)
            try:
                r = C.cargar_capa(rutas, nombre, rol, fuente, campo or None, usuario()["usuario"])
                st.success(f"Capa cargada ({r['formato']}, {r['elementos'] or 0} elementos, {r['crs'] or 'sin CRS'}).")
            except Exception as e:
                st.error(str(e))


def _listado():
    capas = C.listar()
    if not capas:
        st.info("No hay capas cargadas todavía.")
        return
    df = pd.DataFrame(capas)[["id", "nombre", "rol", "formato", "crs", "n_elementos", "campo_clave",
                              "fuente", "cargado_por", "fecha"]]
    st.dataframe(df, use_container_width=True, hide_index=True)
    if puede("cargar_capa"):
        cid = st.selectbox("Capa", [c["id"] for c in capas],
                           format_func=lambda i: next(c["nombre"] for c in capas if c["id"] == i))
        motivo = confirmar_eliminacion(f"capa_{cid}", "esta capa")
        if motivo:
            C.eliminar(cid, usuario()["usuario"], motivo)
            st.success("Capa eliminada y registrada en auditoría.")
            st.rerun()


def _mapa(predio=None):
    try:
        import folium
        from streamlit_folium import st_folium
    except ImportError:
        st.caption("Instale folium y streamlit-folium para ver el mapa interactivo.")
        return
    import geopandas as gpd
    m = folium.Map(location=[6.08, -75.33], zoom_start=13, tiles="OpenStreetMap")
    for c in C.listar():
        if c["formato"] in ("geotiff", "referencia"):
            continue
        try:
            g = gpd.read_file(c["archivo"]).to_crs("EPSG:4326")
            folium.GeoJson(g.to_json(), name=c["nombre"]).add_to(m)
        except Exception as e:
            st.caption(f"No se pudo dibujar {c['nombre']}: {e}")
    if predio is not None:
        folium.GeoJson(predio.to_crs("EPSG:4326").to_json(), name="Predio",
                       style_function=lambda _: {"color": "red", "weight": 3}).add_to(m)
    folium.LayerControl().add_to(m)
    st_folium(m, height=520, use_container_width=True)


def _cruce():
    st.subheader("Cruce del predio con la cartografía cargada")
    st.caption("Suba el polígono del predio o del proyecto (GeoJSON, KML, GPKG, shapefile en .zip; "
               "el DXF se habilitará en el módulo de análisis de planos).")
    archivos = st.file_uploader("Polígono del predio", type=FORMATOS, accept_multiple_files=True, key="predio")
    if not archivos:
        _mapa()
        return
    try:
        predio = C.leer_predio(guardar_subidos(archivos))
    except Exception as e:
        st.error(str(e))
        return
    ap = C.area_perimetro(predio)
    st.metric("Área del predio", f"{ap['area_m2']:,.2f} m²".replace(",", "."))
    st.caption(f"Perímetro {ap['perimetro_m']:,.2f} m · {ap['crs']}")
    resultados = C.cruzar_predio(predio)
    for r in resultados:
        icono = "🔴" if r["afecta"] and r["rol"] in ("riesgo", "rondas_hidricas", "areas_protegidas",
                                                    "mancha_inundacion_tr100") else ("🟡" if r["afecta"] else "⚪")
        with st.expander(f"{icono} {r['rol_descripcion']} — {r['capa']}"):
            if not r["intersecciones"]:
                st.write("No afecta el predio.")
            else:
                st.dataframe(pd.DataFrame([{k: v for k, v in i.items() if k != "atributos"}
                                           for i in r["intersecciones"]]), hide_index=True)
            if r["fuente"]:
                st.caption(f"Fuente: {r['fuente']}")
    faltan = C.roles_faltantes()
    if faltan:
        st.info("No se pudo revisar: " + ", ".join(C.ROLES[f][0] for f in faltan) + " (capa no cargada).")
    _mapa(predio)


def mostrar():
    st.title("Cartografía")
    _estado()
    t1, t2, t3 = st.tabs(["Cruce del predio", "Capas cargadas", "Cargar capa"])
    with t1:
        _cruce()
    with t2:
        _listado()
    with t3:
        if exigir("cargar_capa"):
            _cargar()
