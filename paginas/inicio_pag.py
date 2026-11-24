"""Inicio por tareas y perfiles (propuesta C de la interfaz).

Arriba: saludo, perfil y buscador único. Luego las tareas grandes del perfil,
los pendientes ordenados por vencimiento con su siguiente paso, y los avisos
del sistema. Cada botón lleva a la página correspondiente con el trámite ya
seleccionado.
"""
from datetime import datetime

import pandas as pd
import streamlit as st

from core import inicio as I
from core import parametros as P
from paginas.comun import usuario

COLOR_NIVEL = {"vencido": "#B42318", "urgente": "#B42318", "pronto": "#92400E", "normal": "#55606E"}


def ir_a(pagina: str, tramite_id: int | None = None, expediente_id: int | None = None):
    """Callback de navegación: se ejecuta antes de redibujar, así el menú lateral cambia sin error."""
    st.session_state["pagina"] = pagina
    if tramite_id:
        st.session_state["tramite_foco"] = tramite_id
    if expediente_id:
        st.session_state["expediente_abierto"] = expediente_id


def _saludo() -> str:
    h = datetime.now().hour
    return "Buenos días" if h < 12 else ("Buenas tardes" if h < 19 else "Buenas noches")


def _perfil(u: dict) -> str:
    opciones = I.perfiles_visibles(u["rol"])
    if len(opciones) == 1:
        return opciones[0]
    actual = st.session_state.get("vista_perfil", u["rol"])
    return st.radio("Ver la pantalla de", opciones, index=opciones.index(actual) if actual in opciones else len(opciones) - 1,
                    format_func=I.PERFILES.get, horizontal=True, key="vista_perfil",
                    help="Muestra lo que ve cada perfil. No cambia sus permisos.")


def _buscador(perfil: str):
    texto = st.text_input("Escriba un predio, radicado o pregunta normativa",
                          placeholder="Ej.: 020-12345 · 05148-0-26-0142 · S1-CN-1 · ¿cuántos pisos en consolidación?",
                          key="buscador_inicio")
    r = I.buscar(texto)
    if r["tipo"] == "vacio":
        return
    with st.container(border=True):
        if r.get("expedientes") and perfil != "consulta":
            st.markdown("**Expedientes**")
            for e in r["expedientes"]:
                c1, c2 = st.columns([5, 1])
                c1.markdown(f"{e['radicado']} · {e['solicitante']} · {e.get('direccion') or 'sin dirección'} · "
                            f"matrícula {e.get('matricula') or '—'}")
                c2.button("Abrir", key=f"bx{e['id']}", on_click=ir_a, args=("Expedientes y trámites", None, e["id"]),
                          use_container_width=True)
        if r["tipo"] == "poligono":
            st.markdown(f"**Ficha del polígono {r['codigo']}**")
            filas = [{"Sección": sec, "Dato": i["etiqueta"], "Valor": i["valor"], "Fuente": i["fuente"]}
                     for sec, items in r["ficha"]["secciones"].items() if sec != "Usos del suelo" for i in items][:14]
            if filas:
                st.dataframe(pd.DataFrame(filas).astype(str), hide_index=True, use_container_width=True)
            st.button("Ver ficha completa en Consulta normativa", on_click=ir_a, args=("Consulta normativa",))
        elif r["tipo"] == "norma":
            res = r["resultado"]
            n = sum(len(v) for v in res.values())
            if not n and not r.get("expedientes"):
                st.info("Sin resultados. Pruebe con otra palabra (ej.: retiro, altura, cesión, apique).")
            for p in res.get("parametros", [])[:5]:
                st.markdown(f"- **{p['clave'].split('.')[-1].replace('_', ' ')}**: {p['valor']} {p['unidad'] or ''} "
                            f"— *{p['fuente']}*")
            for a in res.get("articulos", [])[:3]:
                st.markdown(f"- {a['norma']} art. {a['articulo']}: {str(a['texto'])[:180]}…")
            if n:
                st.button(f"Ver los {n} resultados en Consulta normativa", on_click=ir_a, args=("Consulta normativa",))


def _tareas(perfil: str, rol: str):
    ts = I.tareas(perfil, rol)
    for i in range(0, len(ts), 3):
        cols = st.columns(3)
        for col, (n, t) in zip(cols, enumerate(ts[i:i + 3], start=i + 1)):
            with col.container(border=True):
                st.markdown(f"#### {n}. {t['titulo']}")
                st.caption(t["sub"])
                st.button("Abrir", key=f"tarea_{t['clave']}", on_click=ir_a, args=(t["pagina"],),
                          use_container_width=True, type="primary" if n == 1 else "secondary")


def _pendientes(u: dict):
    c1, c2 = st.columns([3, 2])
    c1.subheader("Mis pendientes")
    solo = c2.toggle("Solo los míos (responsable)", value=False, key="solo_mios")
    lista = I.pendientes(u, solo_mios=solo)
    if not lista:
        st.info("No hay trámites abiertos" + (" a su nombre." if solo else "."))
        return
    for p in lista:
        with st.container(border=True):
            a, b, c = st.columns([5, 2, 1.4])
            a.markdown(f"**{p['tipo']} · {p['radicado']}**  \n{p['solicitante']} · {p['paso']['texto']}")
            b.markdown(f"<span style='color:{COLOR_NIVEL[p['nivel']]};font-weight:600'>{p['plazo']}</span>",
                       unsafe_allow_html=True)
            c.button(p["paso"]["accion"], key=f"pend{p['tramite_id']}", use_container_width=True,
                     on_click=ir_a, args=(p["paso"]["pagina"], p["tramite_id"], p["expediente_id"]))


def _avisos():
    st.subheader("Avisos del sistema")
    avs = I.avisos()
    if not avs:
        st.success("Todo configurado.")
    for i, a in enumerate(avs):
        with st.container(border=True):
            st.markdown(a["texto"])
            st.button("Ir", key=f"aviso{i}", on_click=ir_a, args=(a["pagina"],))


def mostrar():
    u = usuario()
    c1, c2 = st.columns([3, 2])
    with c1:
        st.title(f"{_saludo()}. ¿Qué quiere hacer hoy?")
    with c2:
        perfil = _perfil(u)
    _buscador(perfil)
    _tareas(perfil, u["rol"])
    st.write("")
    if perfil == "consulta":
        st.info(f"Amenaza sísmica del municipio: Aa = {P.valor('nsr10.amenaza_sismica_municipio.Aa')}, "
                f"Av = {P.valor('nsr10.amenaza_sismica_municipio.Av')} "
                f"({P.obtener('nsr10.amenaza_sismica_municipio.Aa').fuente}). "
                "Los requisitos de cada trámite están en Consulta normativa → Requisitos por trámite.")
        return
    izq, der = st.columns([3, 2])
    with izq:
        _pendientes(u)
    with der:
        _avisos()
