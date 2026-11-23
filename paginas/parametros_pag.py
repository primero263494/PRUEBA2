"""Página: ver y modificar los parámetros normativos (con motivo y auditoría)."""
import json

import pandas as pd
import streamlit as st

from core import parametros as P
from paginas.comun import cita, puede, usuario

NOMBRES = {
    "nacional": "Nacional (Ley 388 / Decreto 1077)",
    "nsr10": "NSR-10",
    "pbot": "PBOT (Acuerdo 012/2017)",
    "d152": "Decreto 152/2018",
    "tarifas": "Tarifas 2026",
    "tramites": "Catálogo de trámites",
    "listas": "Listas de chequeo",
}

# Parámetros con varias opciones normativas (decisiones de la Secretaría)
OPCIONES_CLAVE = [
    "pbot.definiciones.area_neta",
    "pbot.definiciones.base_indice_ocupacion",
    "pbot.definiciones.base_indice_construccion",
    "pbot.indice_construccion_maximo",
    "pbot.plusvalia.tasa_participacion",
    "tarifas.bases.regla_redondeo",
]


def _fmt(v):
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)[:120]
    return "—" if v is None else str(v)


def _editor_opciones(p: P.Parametro):
    etiquetas = {str(o["id"]): o.get("etiqueta", str(o["id"])) for o in p.opciones}
    ids = list(etiquetas)
    actual = str(p.valor) if str(p.valor) in ids else ids[0]
    st.markdown(f"**{p.clave}**")
    eleccion = st.radio("Opción aplicada", ids, index=ids.index(actual),
                        format_func=lambda i: etiquetas[i], key=f"op_{p.clave}",
                        disabled=not puede("*"))
    elegida = next(o for o in p.opciones if str(o["id"]) == eleccion)
    if elegida.get("formula"):
        st.code(elegida["formula"], language=None)
    if elegida.get("nota"):
        st.caption(elegida["nota"])
    if elegida.get("advertencia"):
        st.warning(elegida["advertencia"])
    if p.nota:
        st.info(p.nota)
    cita(p.fuente)
    if p.origen == "modificado":
        m = p.modificacion
        st.caption(f"Modificado por {m['usuario']} el {m['fecha']}: {m['motivo']}")
    if puede("*") and eleccion != actual:
        motivo = st.text_input("Motivo / acto que soporta el cambio", key=f"mot_{p.clave}")
        if st.button("Aplicar opción", key=f"ap_{p.clave}"):
            try:
                P.modificar(p.clave, eleccion, usuario()["usuario"], motivo)
                st.success("Opción aplicada y registrada.")
                st.rerun()
            except Exception as e:
                st.error(str(e))
    st.divider()


def _seccion_opciones():
    st.subheader("Definiciones con varias opciones normativas")
    st.caption("Por defecto se aplica la norma de mayor jerarquía. Solo el administrador cambia la opción; "
               "queda registrado con motivo.")
    for clave in OPCIONES_CLAVE:
        _editor_opciones(P.obtener(clave))


def _seccion_tarifas():
    st.subheader("Tarifas de delineación 2026 (por m² construido)")
    regla = P.obtener("tarifas.bases.regla_redondeo")
    st.caption(f"Criterio de redondeo aplicado: {regla.opcion_elegida()['etiqueta']}")
    filas = []
    claves = [c.split(".")[-1] for c in P.todos() if c.startswith("tarifas.delineacion_m2.")]
    for c in claves:
        t = P.tarifa_m2(c)
        filas.append({
            "Uso": c.replace("_", " "), "UVT × factor": t["exacto"], "Valor del decreto": t["decreto"],
            "Millar superior (art. 2)": t["millar_superior"], "Valor aplicado": t["aplicado"],
            "Nota": t["nota"] or "",
        })
    df = pd.DataFrame(filas)
    st.dataframe(df, use_container_width=True, hide_index=True)
    for p in P.alertas_tarifas():
        st.warning(f"{p.clave.split('.')[-1]}: {p.nota}")
    if puede("*"):
        with st.expander("Modificar una tarifa"):
            c = st.selectbox("Tarifa", claves, format_func=lambda x: x.replace("_", " "))
            p = P.obtener(f"tarifas.delineacion_m2.{c}")
            nuevo = st.number_input("Nuevo valor por m² ($)", min_value=0, value=int(p.valor), step=1000)
            motivo = st.text_input("Motivo / acto (ej. corrección Hacienda)", key="mot_tarifa")
            col1, col2 = st.columns(2)
            if col1.button("Guardar tarifa"):
                try:
                    P.modificar(p.clave, int(nuevo), usuario()["usuario"], motivo)
                    st.success("Tarifa modificada.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
            if p.origen == "modificado" and col2.button("Volver al valor del decreto"):
                P.restaurar(p.clave, usuario()["usuario"], motivo or "Restaurar valor del decreto")
                st.rerun()


def _seccion_tabla(alias: str):
    filas = []
    for c, p in P.todos().items():
        if not c.startswith(alias + "."):
            continue
        filas.append({"Clave": c[len(alias) + 1:], "Valor aplicado": _fmt(p.valor_numerico()),
                      "Unidad": p.unidad or "", "Fuente": p.fuente,
                      "Estado": "PENDIENTE" if p.pendiente else ("Modificado" if p.origen == "modificado" else ""),
                      "Nota": (p.nota or "")[:160]})
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
    md = P.metadatos(alias)
    if md:
        st.caption(" · ".join(f"{k}: {v}" for k, v in md.items() if not isinstance(v, (dict, list))))

    if puede("*"):
        with st.expander("Modificar un parámetro de esta norma"):
            candidatos = [c for c, p in P.todos().items() if c.startswith(alias + ".") and p.editable and not p.opciones]
            c = st.selectbox("Parámetro", candidatos, key=f"sel_{alias}")
            p = P.obtener(c)
            st.write(f"Valor del archivo: `{_fmt(p.valor_archivo)}` · aplicado: `{_fmt(p.valor)}`")
            cita(p.fuente)
            if isinstance(p.valor_archivo, bool):
                nuevo = st.checkbox("Valor", value=bool(p.valor), key=f"bool_{alias}")
            elif isinstance(p.valor_archivo, (int, float)) or p.valor_archivo is None:
                nuevo = st.number_input("Nuevo valor", value=float(p.valor or 0), format="%.4f", key=f"num_{alias}")
            else:
                texto = st.text_area("Nuevo valor (JSON)", value=json.dumps(p.valor, ensure_ascii=False), key=f"txt_{alias}")
                try:
                    nuevo = json.loads(texto)
                except json.JSONDecodeError:
                    nuevo = texto
            motivo = st.text_input("Motivo / acto que soporta el cambio", key=f"motp_{alias}")
            if st.button("Guardar", key=f"g_{alias}"):
                try:
                    P.modificar(c, nuevo, usuario()["usuario"], motivo)
                    st.success("Guardado y registrado en auditoría.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))


def mostrar():
    st.title("Parámetros normativos")
    st.caption("Todo cálculo del programa usa estos valores, con su norma y artículo. "
               "El archivo base está en config/parametros; los cambios hechos aquí quedan con motivo y usuario.")
    pend = P.pendientes()
    if pend:
        with st.expander(f"{len(pend)} parámetros pendientes de completar"):
            for p in pend:
                st.markdown(f"- **{p.clave}** — {p.nota or 'sin valor'}  \n  _{p.fuente}_")

    pestañas = st.tabs(["Opciones normativas", "Tarifas 2026"] + [NOMBRES[a] for a in P.ARCHIVOS])
    with pestañas[0]:
        _seccion_opciones()
    with pestañas[1]:
        _seccion_tarifas()
    for i, alias in enumerate(P.ARCHIVOS, start=2):
        with pestañas[i]:
            _seccion_tabla(alias)
