"""Página: análisis de planos y estudios (arquitectónicos, estructurales,
geotécnicos, topográficos y ambientales)."""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from core import conversores, db, documentos as D, expedientes as E, lectura, sismo
from core import parametros as P
from core.planos import analisis as A, lectores
from paginas.comun import guardar_subidos, indice_foco, puede, usuario

COLOR = {"CUMPLE": "#e5f4e4", "NO CUMPLE": "#fbebeb", "REVISAR": "#f9eeda", "NO VERIFICABLE": "#f0efec", "INFO": "#e7f1fb"}
DISCIPLINAS = ["arquitectonico", "estructural", "geotecnico", "topografico", "ambiental", "sig", "sin_clasificar"]
NIVELES = [
    ("Lectura completa", "DXF; DWG convertido (ODA o LibreDWG); IFC 2x3/4; .e2k (ETABS), .s2k (SAP2000), .f2k (SAFE); "
     "Excel/CSV (derivas, sondeos); AGS4; SIG (SHP en .zip, GeoJSON, KML, GPKG)", "Mide y compara automáticamente"),
    ("Lectura de texto", "PDF digital o escaneado, imágenes (JPG, PNG, TIFF), Word — OCR local o IA",
     "Extrae Aa, Av, perfil, f'c, fy, derivas, sondeos, capacidad portante, cuadro de áreas y matrículas"),
    ("Formato cerrado", "RVT, SKP, PLN, EDB, SDB, FDB, CYPECAD, Robot, gINT, DGN",
     "Indica qué exportación abierta pedir al solicitante"),
]


def _valor(txt):
    if isinstance(txt, (int, float)):
        return txt
    s = str(txt).strip()
    if s == "":
        return None
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        from core.planos.util import num
        n = num(s)
        return n if n is not None and s.replace(",", ".").replace(" ", "").lstrip("-").replace(".", "", 1).isdigit() else s


def _tabla_datos(lecturas):
    filas = []
    for i, r in enumerate(lecturas):
        for k, v in r["datos"].items():
            if k == "lote_puntos_9377":
                continue
            val = v["valor"]
            filas.append({"n": i, "Archivo": r["archivo"], "Disciplina": r["disciplina"], "Dato": k,
                          "Valor": json.dumps(val, ensure_ascii=False) if isinstance(val, (list, dict)) else str(val),
                          "Unidad": v.get("unidad", ""), "Evidencia": v.get("evidencia", "")})
    return pd.DataFrame(filas)


def _aplicar_correcciones(lecturas, df):
    nuevas = [dict(r, datos={k: v for k, v in r["datos"].items() if k == "lote_puntos_9377"}) for r in lecturas]
    for _, f in df.iterrows():
        if pd.isna(f.get("n")) or not str(f.get("Dato") or "").strip():
            continue
        r = nuevas[int(f["n"])]
        r["disciplina"] = f["Disciplina"] or r["disciplina"]
        r["datos"][f["Dato"].strip()] = {"valor": _valor(f["Valor"]), "unidad": f.get("Unidad") or "",
                                         "evidencia": f.get("Evidencia") or "Ingresado por el revisor"}
    return nuevas


def _resultados(res):
    c = res["concepto"]
    st.subheader(f"Concepto sugerido: {c['sugerido']}")
    cols = st.columns(5)
    for col, k in zip(cols, ["CUMPLE", "NO CUMPLE", "REVISAR", "NO VERIFICABLE", "INFO"]):
        col.metric(k.capitalize(), c["conteo"].get(k, 0))
    df = pd.DataFrame(res["items"]).rename(columns={"disciplina": "Disciplina", "item": "Ítem", "estado": "Estado",
                                                    "detalle": "Detalle", "norma": "Norma", "evidencia": "Evidencia"})
    st.dataframe(df.style.map(lambda v: f"background-color: {COLOR.get(v, '')}", subset=["Estado"]),
                 hide_index=True, use_container_width=True)
    st.markdown("**Borrador del concepto**")
    st.write(c["texto"])
    if c["observaciones"]:
        st.markdown("**Observaciones (no cumple)**")
        for o in c["observaciones"]:
            st.markdown(f"- {o}")


def _herramientas_rapidas():
    with st.expander("Verificación rápida sísmica y geotécnica (sin archivos)"):
        c1, c2, c3, c4 = st.columns(4)
        perfil = c1.selectbox("Perfil de suelo", ["A", "B", "C", "D", "E"], index=3)
        grupo = c2.selectbox("Grupo de uso", ["I", "II", "III", "IV"])
        aa = c3.number_input("Aa declarado", value=0.15, step=0.05, format="%.2f")
        av = c4.number_input("Av declarado", value=0.20, step=0.05, format="%.2f")
        esp = sismo.espectro(perfil, grupo)
        st.table(pd.DataFrame([
            {"Ítem": "Aa", "Memoria": aa, "Norma": esp["Aa"], "Resultado": "CUMPLE" if aa >= esp["Aa"] else "NO CUMPLE"},
            {"Ítem": "Av", "Memoria": av, "Norma": esp["Av"], "Resultado": "CUMPLE" if av >= esp["Av"] else "NO CUMPLE"},
            {"Ítem": "Fa / Fv / I", "Memoria": "", "Norma": f"{esp['Fa']} / {esp['Fv']} / {esp['I']}", "Resultado": ""},
            {"Ítem": "TC (s) / Sa meseta (g)", "Memoria": "", "Norma": f"{esp['TC']} / {esp['Sa_meseta']}", "Resultado": ""},
        ]).astype(str))
        c1, c2 = st.columns(2)
        niveles = c1.number_input("Niveles", min_value=1, value=3)
        carga = c2.number_input("Carga máxima en columna (kN, 0 si no se conoce)", min_value=0.0, value=0.0)
        cat = sismo.categoria_unidad(int(niveles), carga or None)
        req = sismo.sondeos_minimos(cat)
        st.caption(f"Categoría {cat}: mínimo {req['numero']} sondeos a {req['profundidad_m']} m (NSR-10 H.3.1-1 y H.3.2-1).")


def mostrar():
    st.title("Análisis de planos y estudios")
    st.dataframe(pd.DataFrame(NIVELES, columns=["Nivel", "Formatos", "Qué hace el programa"]), hide_index=True,
                 use_container_width=True)
    disp = conversores.disponibles()
    modo, expl = lectura.modo_efectivo()
    st.caption(f"DWG — ODA: {'sí' if disp['oda'] else 'no'} · LibreDWG: {'sí' if disp['libredwg'] else 'no'} · "
               f"Escaneos: {modo} ({expl})")
    _herramientas_rapidas()

    filas = db.consultar("SELECT t.id, t.tipo, e.radicado FROM tramites t JOIN expedientes e ON e.id=t.expediente_id "
                         "ORDER BY t.id DESC LIMIT 300")
    opciones = {0: "(sin trámite — análisis libre)"} | {f["id"]: f"#{f['id']} · {f['radicado']} · {E.tipos()[f['tipo']]['nombre']}"
                                                         for f in filas}
    tid = st.selectbox("Trámite", list(opciones), format_func=opciones.get, index=indice_foco(list(opciones)))
    tr = E.tramite(tid) if tid else None
    exp = E.obtener(tr["expediente_id"]) if tr else None

    archivos: list[tuple[Path, str]] = []
    if tr:
        docs = [d for d in D.listar(exp["id"]) if d["tramite_id"] in (tid, None)]
        elegibles = {d["id"]: f"{d['nombre_original']} ({D.catalogo()[d['tipo_documento']]['nombre']})" for d in docs}
        sel = st.multiselect("Documentos del trámite a analizar", list(elegibles), format_func=elegibles.get,
                             default=[d["id"] for d in docs if d["extension"] in lectores.COMPLETA | lectores.TEXTO][:12])
        archivos += [(Path(D.obtener(i)["archivo"]), D.obtener(i)["nombre_original"]) for i in sel]
    subidos = st.file_uploader("Agregar archivos (cualquier formato)", accept_multiple_files=True)
    guardar_docs = bool(tr) and st.checkbox("Guardar también los archivos agregados en el expediente", value=True)
    forzar = st.selectbox("Lectura de escaneos para este análisis", ["(según Configuración)", "local", "ia"])

    if st.button("Leer archivos", type="primary") and (archivos or subidos):
        rutas = guardar_subidos(subidos)
        for ruta, s in zip(rutas, subidos or []):
            if guardar_docs:
                try:
                    r = D.subir(ruta, exp["id"], tid, None, usuario()["usuario"], nombre_original=s.name)
                    archivos.append((Path(r["ruta"]), s.name))
                    continue
                except Exception as e:
                    st.warning(f"{s.name}: no se guardó en el expediente ({e}); se analiza igual.")
            archivos.append((ruta, s.name))
        with st.spinner("Leyendo planos y estudios…"):
            st.session_state["planos_lecturas"] = [
                lectores.analizar(r, n, None if forzar.startswith("(") else forzar) for r, n in archivos]
        st.session_state["planos_tramite"] = tid

    lecturas = st.session_state.get("planos_lecturas")
    if not lecturas or st.session_state.get("planos_tramite") != tid:
        if tr:
            prev = A.ultimo(tid)
            if prev:
                st.info(f"Último análisis guardado: {prev['fecha']} por {prev['usuario']} — {prev['concepto']['sugerido']}")
        return

    st.subheader("1. Lectura de cada archivo")
    st.dataframe(pd.DataFrame([{"Archivo": r["archivo"], "Nivel": r["nivel"], "Disciplina": r["disciplina"],
                                "Datos": len(r["datos"]), "Avisos": " ".join(r["avisos"])} for r in lecturas]),
                 hide_index=True, use_container_width=True)
    with st.expander("Detalle técnico de la lectura"):
        for r in lecturas:
            st.markdown(f"**{r['archivo']}**")
            st.json(r["resumen"], expanded=False)

    st.subheader("2. Datos extraídos (corrija lo que el programa leyó mal)")
    st.caption("Cada dato trae su evidencia. Puede cambiar el valor, la disciplina o agregar filas con datos que el programa "
               "no encontró (use el número de archivo de la columna n).")
    df = _tabla_datos(lecturas)
    if df.empty:
        df = pd.DataFrame(columns=["n", "Archivo", "Disciplina", "Dato", "Valor", "Unidad", "Evidencia"])
    ed = st.data_editor(df, num_rows="dynamic", hide_index=True, use_container_width=True, key="planos_ed",
                        column_config={"n": st.column_config.NumberColumn("n", min_value=0, max_value=len(lecturas) - 1, step=1),
                                       "Disciplina": st.column_config.SelectboxColumn(options=DISCIPLINAS),
                                       "Archivo": st.column_config.TextColumn(disabled=True)})
    corregidas = _aplicar_correcciones(lecturas, ed)

    st.subheader("3. Verificación, cruce y concepto")
    res = A.evaluar(corregidas, exp, tr)
    _resultados(res)
    if tr and puede("analizar_planos") and st.button("Guardar análisis en el trámite"):
        A.guardar(tid, corregidas, res, usuario()["usuario"])
        st.success("Análisis guardado. Aparecerá en el informe técnico del trámite.")
