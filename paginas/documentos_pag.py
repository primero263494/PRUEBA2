"""Página: gestión documental (módulo 3).

`panel_expediente(eid)` se muestra como pestaña dentro de cada expediente;
`mostrar()` es la página general para buscar documentos de todos los expedientes.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

from core import db, documentos as D, expedientes as E, vista_previa
from paginas.comun import confirmar_eliminacion, guardar_subidos, puede, usuario


def _tam(b: int) -> str:
    return f"{b / 1024:,.0f} KB" if b < 1024 * 1024 else f"{b / 1024 / 1024:,.1f} MB"


def _vista(doc: dict):
    st.markdown(f"**{doc['nombre_original']}** · v{doc['version']} · {_tam(doc['tamano'])} · "
                f"cargado por {doc['cargado_por']} el {doc['fecha']}")
    ruta = Path(doc["archivo"])
    if ruta.exists():
        st.download_button("Descargar", ruta.read_bytes(), file_name=doc["nombre_original"], key=f"dl{doc['id']}")
    pagina = 1
    if doc["extension"] == "pdf":
        pagina = st.number_input("Desde la página", min_value=1, value=1, key=f"pg{doc['id']}")
    v = vista_previa.generar(ruta, doc["extension"], pagina)
    if v["tipo"] == "imagenes":
        if v.get("paginas"):
            st.caption(f"{v['paginas']} páginas")
        for img in v["imagenes"]:
            st.image(str(img), use_container_width=True)
    elif v["tipo"] == "texto":
        st.text(v["texto"])
        for t in v.get("tablas", []):
            st.dataframe(pd.DataFrame(t), hide_index=True)
    elif v["tipo"] == "tablas":
        for nombre, df in v["tablas"].items():
            st.caption(f"Hoja: {nombre}")
            st.dataframe(df, hide_index=True)
    elif v["tipo"] == "dxf":
        if v.get("nota"):
            st.caption(v["nota"])
        st.caption(f"DXF {v['version']} · unidades: {v['unidades']} · {len(v['capas'])} capas")
        if v.get("imagen"):
            st.image(str(v["imagen"]), use_container_width=True)
        c1, c2 = st.columns(2)
        c1.dataframe(pd.DataFrame(sorted(v["entidades"].items(), key=lambda x: -x[1]), columns=["Entidad", "Cantidad"]),
                     hide_index=True)
        c2.dataframe(pd.DataFrame({"Capas": v["capas"]}), hide_index=True)
        if v["textos"]:
            with st.expander("Textos del plano"):
                st.write(v["textos"])
    else:
        st.info(v.get("mensaje", "Sin vista previa."))


def panel_expediente(eid: int):
    exp = E.obtener(eid)
    trs = E.tramites(eid)
    cat = D.catalogo()
    opciones_tr = {0: "General del expediente"} | {t["id"]: f"#{t['id']} {E.tipos()[t['tipo']]['nombre']}" for t in trs}

    # Documentos exigidos por trámite
    for t in trs:
        f = D.faltantes(exp, t)
        ok = sum(1 for x in f if x["cargado"])
        with st.expander(f"Exigidos para #{t['id']} {E.tipos()[t['tipo']]['nombre']}: {ok} de {len(f)} cargados"):
            st.dataframe(pd.DataFrame([{"Documento": x["nombre"], "Cargado": "Sí" if x["cargado"] else "Falta"} for x in f]),
                         hide_index=True, use_container_width=True)
            for v in D.vencidos(exp, t):
                st.warning(f"{cat[v['tipo_documento']]['nombre']}: expedido {v['edad_dias']} días antes de la radicación "
                           f"(máximo {v['vigencia_dias']}).")

    if puede("expedientes"):
        with st.expander("Subir documentos", expanded=not D.listar(eid)):
            subidos = st.file_uploader("Archivos (PDF, imágenes, Word, Excel, DWG/DXF, IFC, ETABS/SAP, SIG…)",
                                       type=D.extensiones(), accept_multiple_files=True, key=f"up{eid}")
            c1, c2 = st.columns(2)
            tid = c1.selectbox("Trámite", list(opciones_tr), format_func=opciones_tr.get, key=f"uptr{eid}")
            fecha = c2.text_input("Fecha de expedición (AAAA-MM-DD, si aplica)", key=f"upf{eid}")
            asignaciones = {}
            if subidos:
                st.caption("Tipo sugerido según el nombre del archivo; cámbielo si no corresponde.")
                claves = list(cat)
                for s in subidos:
                    sug = D.sugerir_tipo(s.name)
                    asignaciones[s.name] = st.selectbox(s.name, claves, index=claves.index(sug),
                                                        format_func=lambda k: cat[k]["nombre"], key=f"tipo_{eid}_{s.name}")
            if subidos and st.button("Guardar documentos", type="primary", key=f"gd{eid}"):
                for ruta, s in zip(guardar_subidos(subidos), subidos):
                    try:
                        r = D.subir(ruta, eid, tid or None, asignaciones[s.name], usuario()["usuario"],
                                    fecha or None, nombre_original=s.name)
                        msg = f"{s.name} → {cat[r['tipo']]['nombre']} (v{r['version']})"
                        if r["duplicado_de"]:
                            msg += f" · ojo: es idéntico a '{r['duplicado_de']['nombre_original']}'"
                        st.success(msg)
                    except Exception as e:
                        st.error(f"{s.name}: {e}")
                st.rerun()

    docs = D.listar(eid)
    if not docs:
        st.info("Sin documentos cargados.")
        return
    df = pd.DataFrame([{"id": d["id"], "Trámite": opciones_tr.get(d["tramite_id"] or 0, "—"),
                        "Tipo": cat.get(d["tipo_documento"], {}).get("nombre", d["tipo_documento"]),
                        "Archivo": d["nombre_original"], "Versión": d["version"], "Tamaño": _tam(d["tamano"]),
                        "Expedición": d["fecha_expedicion"] or "", "Cargado": d["fecha"]} for d in docs])
    st.dataframe(df, hide_index=True, use_container_width=True)
    did = st.selectbox("Ver documento", [d["id"] for d in docs], key=f"ver{eid}",
                       format_func=lambda i: next(f"{x['nombre_original']} (v{x['version']})" for x in docs if x["id"] == i))
    doc = D.obtener(did)
    _vista(doc)
    if puede("expedientes"):
        with st.expander("Reclasificar o corregir datos"):
            claves = list(cat)
            c1, c2, c3 = st.columns(3)
            tipo = c1.selectbox("Tipo", claves, index=claves.index(doc["tipo_documento"]),
                                format_func=lambda k: cat[k]["nombre"], key=f"rt{did}")
            tr = c2.selectbox("Trámite", list(opciones_tr), index=list(opciones_tr).index(doc["tramite_id"] or 0),
                              format_func=opciones_tr.get, key=f"rtr{did}")
            fe = c3.text_input("Fecha de expedición", doc["fecha_expedicion"] or "", key=f"rfe{did}")
            obs = st.text_input("Observaciones", doc["observaciones"] or "", key=f"robs{did}")
            if st.button("Guardar cambios", key=f"rg{did}"):
                D.editar(did, {"tipo_documento": tipo, "tramite_id": tr or None, "fecha_expedicion": fe or None,
                               "observaciones": obs}, usuario()["usuario"])
                st.success("Documento actualizado (el archivo se movió a la carpeta que corresponde).")
                st.rerun()
        m = confirmar_eliminacion(f"doc{did}", f"el documento '{doc['nombre_original']}'")
        if m:
            D.eliminar(did, usuario()["usuario"], m)
            st.success("Documento eliminado. El archivo quedó en la papelera y el registro en Auditoría.")
            st.rerun()


def mostrar():
    st.title("Gestión documental")
    st.caption("Los documentos se cargan desde cada expediente (pestaña Documentos). Aquí puede buscarlos todos.")
    texto = st.text_input("Buscar por nombre de archivo, radicado o tipo")
    cat = D.catalogo()
    filas = db.consultar(
        "SELECT d.*, e.radicado, e.solicitante FROM documentos d JOIN expedientes e ON e.id=d.expediente_id "
        "WHERE d.nombre_original LIKE ? OR e.radicado LIKE ? OR d.tipo_documento LIKE ? ORDER BY d.id DESC LIMIT 500",
        (f"%{texto}%",) * 3)
    if not filas:
        st.info("No hay documentos.")
        return
    st.dataframe(pd.DataFrame([{"Radicado": f["radicado"], "Solicitante": f["solicitante"],
                                "Tipo": cat.get(f["tipo_documento"], {}).get("nombre", f["tipo_documento"]),
                                "Archivo": f["nombre_original"], "Versión": f["version"], "Cargado": f["fecha"],
                                "Por": f["cargado_por"]} for f in filas]), hide_index=True, use_container_width=True)
    did = st.selectbox("Ver", [f["id"] for f in filas],
                       format_func=lambda i: next(f"{x['radicado']} · {x['nombre_original']}" for x in filas if x["id"] == i))
    _vista(D.obtener(did))
