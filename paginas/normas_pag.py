"""Página: cargar normas (nacionales, municipales, NSR-10, Cornare), buscar
artículos y llevar el normograma con fecha de verificación."""
from datetime import date, datetime

import pandas as pd
import streamlit as st

from core import ajustes, lectura, normas
from core import parametros as P
from paginas.comun import confirmar_eliminacion, exigir, guardar_subidos, puede, usuario, campo_fecha


def _normograma():
    st.subheader("Normograma (vigencia)")
    meses = ajustes.obtener("normograma.meses_alerta_verificacion", 6)
    filas = []
    for n in P.valor("nacional.normograma"):
        ver = n.get("verificado", "")
        vencido = True
        try:
            d = datetime.strptime(ver, "%Y-%m-%d").date()
            vencido = (date.today() - d).days > meses * 30
        except ValueError:
            pass
        filas.append({"Norma": n["norma"], "Versión": n["version"], "Modificaciones": n["modificaciones"],
                      "Verificado": ver, "Revisar": "Sí" if vencido else "", "Enlace": n.get("url", "")})
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True,
                 column_config={"Enlace": st.column_config.LinkColumn("Enlace")})
    st.caption(f"Se marca 'Revisar' lo que lleva más de {meses} meses sin verificar o sigue pendiente. "
               "El programa no consulta internet por sí solo: cargue la versión nueva abajo y márquela como verificada.")


def _cargar():
    st.subheader("Normas base")
    st.caption("Importa al buscador los textos del PBOT, Decreto 152, tarifas 2026, Ley 388 y Decreto 1077 "
               "que vienen con el programa. Las ya importadas no se repiten.")
    if st.button("Cargar normas base"):
        with st.spinner("Importando textos (puede tardar un minuto)…"):
            r = normas.cargar_base(usuario()["usuario"])
        if r:
            for x in r:
                st.success(f"{x['nombre']}: {x['articulos']} artículos")
        else:
            st.info("Las normas base ya estaban cargadas.")
    st.subheader("Cargar norma")
    modo, explicacion = lectura.modo_efectivo()
    st.caption(f"Lectura de escaneos: **{modo}** — {explicacion}")
    with st.form("cargar_norma", clear_on_submit=True):
        archivo = st.file_uploader("Archivo (PDF digital o escaneado, Word, imagen, texto)",
                                   type=["pdf", "docx", "txt", "md", "png", "jpg", "jpeg", "tif", "tiff"])
        nombre = st.text_input("Nombre de la norma", placeholder="NSR-10 Título H")
        c1, c2, c3 = st.columns(3)
        ambito = c1.selectbox("Ámbito", normas.AMBITOS)
        disciplina = c2.selectbox("Disciplina", normas.DISCIPLINAS)
        version = campo_fecha(c3, "Fecha de la versión o compilación", None, key="norma_version")
        forzar = st.selectbox("Forzar modo de lectura", ["(según Configuración)", "local", "ia"])
        if st.form_submit_button("Cargar") and archivo and nombre:
            rutas = guardar_subidos(archivo)
            with st.spinner("Leyendo el documento…"):
                try:
                    r = normas.cargar(rutas[0], nombre, ambito, disciplina, version, usuario()["usuario"],
                                      forzar_modo=None if forzar.startswith("(") else forzar)
                    st.success(f"Norma cargada: {r['articulos']} artículos detectados, lectura {r['metodo']}.")
                    if r["aviso"]:
                        st.info(r["aviso"])
                    if r["articulos"] == 0:
                        st.warning("No se detectaron artículos; la búsqueda funcionará sobre el texto completo "
                                   "solo cuando se agregue esa opción. Revise si el archivo es legible.")
                except Exception as e:
                    st.error(f"No se pudo cargar: {e}")


def _buscar():
    st.subheader("Buscar en las normas cargadas")
    q = st.text_input("Palabra clave o número de artículo", placeholder="ochava, 2.2.6.1.2.3.1, H.3.2")
    if q:
        res = normas.buscar(q)
        st.caption(f"{len(res)} resultados")
        for r in res:
            with st.expander(f"{r['norma']} — art. {r['articulo']} {r['titulo'][:80]}"):
                st.text(r["texto"][:4000])


def _listado():
    st.subheader("Normas cargadas")
    lista = normas.listar()
    if not lista:
        st.info("Aún no hay normas cargadas. Los parámetros ya están en el programa; cargar los textos "
                "habilita el buscador y la cita textual en los conceptos.")
        return
    df = pd.DataFrame(lista)[["id", "nombre", "ambito", "disciplina", "version", "n_articulos",
                              "metodo_lectura", "verificado", "vigente", "cargado_por", "fecha"]]
    st.dataframe(df, use_container_width=True, hide_index=True)
    if puede("cargar_norma"):
        nid = st.selectbox("Norma", [n["id"] for n in lista],
                           format_func=lambda i: next(n["nombre"] for n in lista if n["id"] == i))
        c1, c2 = st.columns(2)
        if c1.button("Marcar como verificada hoy (vigente)"):
            normas.marcar_verificada(nid, usuario()["usuario"], True)
            st.rerun()
        if c2.button("Marcar como derogada / no vigente"):
            normas.marcar_verificada(nid, usuario()["usuario"], False, "Marcada no vigente")
            st.rerun()
        motivo = confirmar_eliminacion(f"norma_{nid}", "esta norma")
        if motivo:
            normas.eliminar(nid, usuario()["usuario"], motivo)
            st.success("Norma eliminada y registrada en auditoría.")
            st.rerun()


def mostrar():
    st.title("Normas")
    t1, t2, t3, t4 = st.tabs(["Normograma", "Buscar", "Normas cargadas", "Cargar"])
    with t1:
        _normograma()
    with t2:
        _buscar()
    with t3:
        _listado()
    with t4:
        if exigir("cargar_norma"):
            _cargar()
