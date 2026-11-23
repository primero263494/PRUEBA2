"""Página: análisis de planos (versión inicial).

Esta versión muestra los niveles de lectura por formato y la verificación
sísmica rápida con la NSR-10 cargada. Los lectores de DXF/IFC/.e2k, el motor
de reglas y el concepto borrador llegan en el módulo de análisis de planos.
"""
import pandas as pd
import streamlit as st

from core import conversores, sismo
from core import parametros as P

NIVELES = [
    ("Lectura completa", "DXF; DWG convertido (ODA o LibreDWG); IFC 2x3/4; .e2k (ETABS), .s2k (SAP2000), "
     ".f2k (SAFE); Excel/CSV (derivas, ensayos, AGS4); SIG (SHP, GeoJSON, KML, GPKG, GeoTIFF)",
     "Mide y compara automáticamente"),
    ("Lectura de texto", "PDF vectorial, PDF escaneado, imágenes (JPG, PNG, TIFF) — OCR local o IA",
     "Extrae cuadros de áreas, cotas, f'c, firmas; geometría con escala calibrada"),
    ("Formato cerrado", "RVT, SKP, PLN, EDB, SDB, FDB, CYPECAD, Robot, Tekla, gINT",
     "Pide al solicitante la exportación abierta (IFC, DXF, .e2k/.s2k, AGS4, PDF)"),
]


def mostrar():
    st.title("Análisis de planos")
    st.dataframe(pd.DataFrame(NIVELES, columns=["Nivel", "Formatos", "Qué hace el programa"]),
                 hide_index=True, use_container_width=True)
    disp = conversores.disponibles()
    st.caption(f"Conversión DWG — ODA: {'sí' if disp['oda'] else 'no instalado'} · "
               f"LibreDWG: {'sí' if disp['libredwg'] else 'no instalado'} (ver Configuración).")

    st.subheader("Verificación sísmica rápida (NSR-10)")
    st.caption("Compare lo que declara la memoria estructural con los valores de la NSR-10 para el municipio.")
    c1, c2, c3, c4 = st.columns(4)
    perfil = c1.selectbox("Perfil de suelo (estudio de suelos)", ["A", "B", "C", "D", "E"], index=3)
    grupo = c2.selectbox("Grupo de uso", ["I", "II", "III", "IV"])
    aa_decl = c3.number_input("Aa declarado en memoria", value=0.15, step=0.05, format="%.2f")
    av_decl = c4.number_input("Av declarado en memoria", value=0.20, step=0.05, format="%.2f")
    esp = sismo.espectro(perfil, grupo)
    aa_n, av_n = esp["Aa"], esp["Av"]
    estado_aa = "CUMPLE" if aa_decl >= aa_n else "NO CUMPLE"
    estado_av = "CUMPLE" if av_decl >= av_n else "NO CUMPLE"
    st.table(pd.DataFrame([
        {"Ítem": "Aa", "Memoria": aa_decl, "Norma": aa_n, "Resultado": estado_aa,
         "Fuente": P.obtener("nsr10.amenaza_sismica_municipio.Aa").fuente},
        {"Ítem": "Av", "Memoria": av_decl, "Norma": av_n, "Resultado": estado_av,
         "Fuente": P.obtener("nsr10.amenaza_sismica_municipio.Av").fuente},
        {"Ítem": "Fa", "Memoria": "", "Norma": esp["Fa"], "Resultado": "", "Fuente": "NSR-10 Tabla A.2.4-3"},
        {"Ítem": "Fv", "Memoria": "", "Norma": esp["Fv"], "Resultado": "", "Fuente": "NSR-10 Tabla A.2.4-4"},
        {"Ítem": "I", "Memoria": "", "Norma": esp["I"], "Resultado": "", "Fuente": "NSR-10 Tabla A.2.5-1"},
        {"Ítem": "TC (s)", "Memoria": "", "Norma": esp["TC"], "Resultado": "", "Fuente": "NSR-10 A.2.6"},
        {"Ítem": "Sa meseta (g)", "Memoria": "", "Norma": esp["Sa_meseta"], "Resultado": "", "Fuente": "NSR-10 A.2.6"},
    ]).astype(str))

    st.subheader("Geotecnia rápida (NSR-10 Título H)")
    c1, c2, c3 = st.columns(3)
    niveles = c1.number_input("Niveles", min_value=1, value=3)
    carga = c2.number_input("Carga máxima de servicio en columna (kN, 0 si no se conoce)", min_value=0.0, value=0.0)
    sondeos_decl = c3.number_input("Sondeos en el estudio", min_value=0, value=3)
    cat = sismo.categoria_unidad(int(niveles), carga or None)
    req = sismo.sondeos_minimos(cat)
    st.write(f"Categoría de la unidad: **{cat}** · mínimo **{req['numero']} sondeos** a "
             f"**{req['profundidad_m']} m** (NSR-10 Tablas H.3.1-1 y H.3.2-1).")
    st.write("Resultado sondeos: " + ("**CUMPLE**" if sondeos_decl >= req["numero"] else "**NO CUMPLE**"))
    st.caption("Este resultado es un borrador de verificación. El concepto lo firma el profesional competente.")
