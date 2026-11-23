"""Informes (módulo 7): informe técnico de revisión y acta de observaciones,
en Word (.docx editable) y PDF, con la plantilla institucional.

El contenido se arma una vez como lista de bloques y se dibuja dos veces:
con python-docx (Word) y con reportlab (PDF). Así el PDF siempre se puede
generar sin Word ni LibreOffice. Si LibreOffice está instalado, también se
puede convertir el Word a PDF para que queden idénticos.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import yaml

from core import auditoria, calculadoras, chequeo, db, documentos, expedientes as E, verificacion as V
from core import parametros as P
from core.planos import analisis as A
from core.rutas import PLANTILLAS

PLANTILLA = PLANTILLAS / "plantilla.yaml"
COLORES = {"CUMPLE": "E5F4E4", "NO CUMPLE": "FBEBEB", "REVISAR": "F9EEDA", "NO VERIFICABLE": "F0EFEC", "INFO": "E7F1FB",
           "Cumple": "E5F4E4", "No cumple": "FBEBEB", "Pendiente": "F9EEDA", "No aplica": "F0EFEC"}

# anchos relativos de columnas por encabezado de tabla (PDF)
ANCHOS = {("Sección", "Ítem", "Estado", "Observación"): [0.2, 0.42, 0.12, 0.26],
          ("Concepto", "Cálculo", "Resultado", "Fuente"): [0.25, 0.25, 0.18, 0.32]}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS informes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tramite_id INTEGER REFERENCES tramites(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL,                 -- informe_tecnico | acta_observaciones
    archivo_docx TEXT, archivo_pdf TEXT,
    conclusion TEXT,
    usuario TEXT NOT NULL,
    fecha TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""


def migrar():
    db.migrar(ESQUEMA)


# ------------------------------------------------------------- plantilla
def plantilla() -> dict:
    return yaml.safe_load(PLANTILLA.read_text(encoding="utf-8")) or {}


def guardar_plantilla(datos: dict, usuario: str) -> None:
    antes = plantilla()
    PLANTILLA.write_text(yaml.safe_dump(datos, allow_unicode=True, sort_keys=False), encoding="utf-8")
    auditoria.registrar(usuario, "editar", "plantilla", "informes", antes=antes, despues=datos)


def guardar_logo(origen: Path, usuario: str) -> str:
    ext = Path(origen).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg"):
        raise ValueError("El logo debe ser PNG o JPG.")
    destino = PLANTILLAS / f"logo{ext}"
    shutil.copy2(origen, destino)
    datos = plantilla()
    datos["logo"] = destino.name
    guardar_plantilla(datos, usuario)
    return str(destino)


def _ruta_logo(pl: dict) -> Path | None:
    if pl.get("logo"):
        r = PLANTILLAS / pl["logo"]
        if r.exists():
            return r
    return None


# --------------------------------------------------------- armado del contenido
def _fmt(v):
    if v is None or v == "":
        return "—"
    if isinstance(v, float):
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def _resumen_calculo(c: dict) -> list:
    """Bloques para un cálculo guardado."""
    r = c["resultado"]
    titulo = {"indices": "Índices de ocupación y construcción", "cuadro_areas": "Cuadro de áreas", "cesiones": "Cesiones urbanísticas",
              "plusvalia": "Participación en plusvalía", "liquidacion": "Liquidación"}.get(c["tipo"], c["tipo"])
    bloques = [("subtitulo", f"{titulo} (guardado el {c['fecha']} por {c['usuario']})")]
    pasos = r.get("pasos") or r.get("pasos_cesiones")
    if c["tipo"] == "cuadro_areas":
        bloques.append(("tabla", ["Concepto", "Área (m²)", "Fuente"],
                        [[f["concepto"], _fmt(f["m2"]), f["fuente"]] for f in r["filas"]], None))
        if r.get("inconsistencias"):
            bloques.append(("lista", r["inconsistencias"]))
    elif pasos:
        bloques.append(("tabla", ["Concepto", "Cálculo", "Resultado", "Fuente"],
                        [[p["concepto"], p.get("calculo", ""), f"{_fmt(p['resultado'])} {p.get('unidad', '')}".strip(), p["fuente"]]
                         for p in pasos], None))
    if c["tipo"] == "plusvalia":
        bloques.append(("parrafo", f"Participación a pagar: ${r['participacion']:,.0f}".replace(",", ".")))
    if c["tipo"] == "liquidacion":
        bloques.append(("parrafo", f"Total liquidado: ${r.get('total', 0):,.0f}".replace(",", ".")))
    return bloques


def contenido_informe(tramite_id: int, conclusion: str = "", observaciones_extra: str = "",
                     incluir_chequeo_completo: bool = True) -> dict:
    tr = E.tramite(tramite_id)
    exp = E.obtener(tr["expediente_id"])
    tipo = E.tipos()[tr["tipo"]]
    b: list = []

    b.append(("titulo", "1. Datos del trámite"))
    datos = [
        ("Radicado", exp["radicado"]), ("Fecha de radicación", tr["fecha_radicacion"]),
        ("Término para resolver (45 días hábiles)", tr["fecha_limite"]),
        ("Trámite", f"{tipo['nombre']} — {tr['modalidad'] or ''}"), ("Estado", tr["estado"]),
        ("Solicitante", f"{exp['solicitante']} ({exp['tipo_persona']}) {exp['documento'] or ''}"),
        ("Dirección del predio", exp["direccion"]), ("Matrícula inmobiliaria", exp["matricula"]),
        ("Cédula catastral", exp["cedula_catastral"]), ("Clase de suelo", exp["clase_suelo"]),
        ("Polígono de tratamiento", exp["poligono"]), ("Área de actividad", exp["area_actividad"]),
        ("Responsable", exp["responsable"]),
    ]
    nombres = P.valor("tramites.campos")
    for k, v in tr["datos"].items():
        datos.append((nombres.get(k, {}).get("etiqueta", k.replace("_", " ").capitalize()), v))
    b.append(("tabla", ["Dato", "Valor"], [[k, _fmt(v)] for k, v in datos], None))

    b.append(("titulo", "2. Verificación normativa"))
    ver = V.verificar(exp, tr)
    res = V.resumen(ver)
    b.append(("parrafo", f"Resultado de la verificación automática: {res['global']}. "
                         + " · ".join(f"{k}: {v}" for k, v in res.items() if k != "global")))
    b.append(("tabla", ["Ítem", "Estado", "Detalle", "Fuente"], [[r["item"], r["estado"], r["detalle"], r["fuente"]] for r in ver], 1))

    b.append(("titulo", "3. Resultados de los cálculos"))
    calcs = calculadoras.listar(tramite_id)
    if calcs:
        vistos = set()
        for c in calcs:                       # el más reciente de cada tipo
            if c["tipo"] in vistos:
                continue
            vistos.add(c["tipo"])
            b += _resumen_calculo(c)
    else:
        b.append(("parrafo", "No se guardaron cálculos para este trámite (Calculadoras → Guardar en el trámite)."))

    b.append(("titulo", "4. Lista de chequeo"))
    chequeo.generar(tramite_id)
    av = chequeo.avance(tramite_id)
    b.append(("parrafo", f"Avance {av['avance']:.0%}: {av['cumple']} cumplen, {av['no_cumple']} no cumplen, "
                         f"{av['no_aplica']} no aplican y {av['pendiente']} pendientes de {av['total']} ítems."))
    secciones = P.valor("listas.secciones")
    items = chequeo.items(tramite_id) if incluir_chequeo_completo else chequeo.observaciones(tramite_id)
    b.append(("tabla", ["Sección", "Ítem", "Estado", "Observación"],
              [[secciones.get(i["seccion"], {}).get("nombre", i["seccion"]), i["texto"], chequeo.ETIQUETAS[i["estado"]],
                i["observacion"] or ""] for i in items], 2))

    b.append(("titulo", "5. Análisis de planos y estudios"))
    an = A.ultimo(tramite_id)
    if an:
        b.append(("parrafo", f"Archivos analizados ({len(an['archivos'])}): {', '.join(an['archivos'])}."))
        b.append(("parrafo", an["concepto"]["texto"]))
        b.append(("tabla", ["Disciplina", "Ítem", "Estado", "Detalle", "Norma"],
                  [[i["disciplina"], i["item"], i["estado"], i["detalle"], i["norma"]] for i in an["resultados"]], 2))
    else:
        b.append(("parrafo", "No se ha guardado un análisis de planos para este trámite."))

    b.append(("titulo", "6. Observaciones"))
    obs = [f"{i['texto']}: {i['observacion']}" for i in chequeo.observaciones(tramite_id)]
    obs += [f"{r['item']}: {r['detalle']} ({r['fuente']})" for r in ver if r["estado"] == V.NO_CUMPLE]
    if an:
        obs += an["concepto"]["observaciones"]
    faltan = [x["nombre"] for x in documentos.faltantes(exp, tr) if not x["cargado"]]
    if faltan:
        obs.append("Documentos por aportar: " + "; ".join(faltan))
    if observaciones_extra.strip():
        obs += [o.strip() for o in observaciones_extra.splitlines() if o.strip()]
    obs = list(dict.fromkeys(obs))
    b.append(("lista", obs) if obs else ("parrafo", "Sin observaciones."))

    b.append(("titulo", "7. Conclusión"))
    sugerida = conclusion_sugerida(ver, av, an, faltan)
    b.append(("parrafo", conclusion.strip() or sugerida))
    b.append(("nota", "Este informe se generó con el programa de trámites urbanísticos a partir de los datos registrados. "
                      "El análisis automático no reemplaza la revisión estructural ni la geotécnica; el concepto lo firma "
                      "el profesional competente (Ley 400 de 1997)."))
    titulo = f"INFORME TÉCNICO DE REVISIÓN — {tipo['nombre'].upper()}"
    return {"titulo": titulo, "subtitulo": f"Radicado {exp['radicado']} · {date.today().isoformat()}", "bloques": b,
            "observaciones": obs, "conclusion_sugerida": sugerida, "tramite": tr, "expediente": exp}


def conclusion_sugerida(ver, av, an, faltan) -> str:
    no_cumple = sum(1 for r in ver if r["estado"] == V.NO_CUMPLE) + av["no_cumple"] + \
        (an["concepto"]["conteo"].get("NO CUMPLE", 0) if an else 0)
    if no_cumple or faltan:
        return ("El proyecto NO es viable en el estado actual. Se requiere que el solicitante atienda las observaciones "
                "del numeral 6 mediante el acta de observaciones y correcciones (Decreto 1077 de 2015, art. 2.2.6.1.2.2.4).")
    if av["pendiente"]:
        return "La revisión está en curso: quedan ítems pendientes en la lista de chequeo antes de emitir concepto."
    return "El proyecto CUMPLE con la norma urbanística revisada y se considera VIABLE, sujeto a la liquidación y pago de las obligaciones."


def contenido_acta(tramite_id: int, observaciones_extra: str = "") -> dict:
    inf = contenido_informe(tramite_id, observaciones_extra=observaciones_extra, incluir_chequeo_completo=False)
    exp, tr = inf["expediente"], inf["tramite"]
    plazo = P.obtener("nacional.licencias.acta_observaciones_plazo_dias_habiles")
    amp = P.valor("nacional.licencias.acta_observaciones_ampliacion_dias_habiles")
    b = [
        ("parrafo", f"Solicitante: {exp['solicitante']} · Predio: {exp['direccion'] or '—'} · Matrícula: {exp['matricula'] or '—'}"),
        ("parrafo", f"Trámite: {E.tipos()[tr['tipo']]['nombre']} ({tr['modalidad'] or ''}), radicado el {tr['fecha_radicacion']}."),
        ("parrafo", "Efectuada la revisión técnica, jurídica, estructural, urbanística y arquitectónica del proyecto, se informa "
                    "al solicitante las actualizaciones, correcciones o aclaraciones que debe realizar y los documentos que "
                    "debe aportar:"),
        ("lista", inf["observaciones"] or ["Sin observaciones."]),
        ("parrafo", f"El solicitante cuenta con {plazo.valor} días hábiles para dar respuesta, ampliables a solicitud de parte "
                    f"hasta por {amp} días hábiles adicionales. Durante este plazo se suspende el término para resolver "
                    f"({plazo.fuente})."),
    ]
    return {"titulo": "ACTA DE OBSERVACIONES Y CORRECCIONES", "subtitulo": f"Radicado {exp['radicado']} · {date.today().isoformat()}",
            "bloques": b, "observaciones": inf["observaciones"], "tramite": tr, "expediente": exp}


# ---------------------------------------------------------------- Word
def _sombrear(celda, color_hex):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    tc = celda._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color_hex)
    tc.append(shd)


def a_word(cont: dict, ruta: Path) -> Path:
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor
    pl = plantilla()
    d = docx.Document()
    sec = d.sections[0]
    sec.left_margin = sec.right_margin = Cm(2.2)
    sec.top_margin, sec.bottom_margin = Cm(2.0), Cm(2.0)
    estilo = d.styles["Normal"]
    estilo.font.name = "Arial"
    estilo.font.size = Pt(10.5)

    # encabezado: logo + entidad + código de formato
    enc = sec.header
    t = enc.add_table(rows=1, cols=3, width=Cm(17))
    logo = _ruta_logo(pl)
    if logo:
        t.cell(0, 0).paragraphs[0].add_run().add_picture(str(logo), height=Cm(1.8))
    else:
        t.cell(0, 0).paragraphs[0].add_run("[LOGO]")
    p = t.cell(0, 1).paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(f"{pl.get('entidad', '')}\n")
    r.bold = True
    p.add_run(pl.get("dependencia", ""))
    p2 = t.cell(0, 2).paragraphs[0]
    p2.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p2.add_run(f"Código: {pl.get('codigo_formato', '')}\nVersión: {pl.get('version_formato', '')}").font.size = Pt(8)
    pie = sec.footer.paragraphs[0]
    pie.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pie.add_run(f"{pl.get('direccion', '')} · {pl.get('telefono', '')} · {pl.get('correo', '')}\n{pl.get('pie', '')}").font.size = Pt(8)

    h = d.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rr = h.add_run(cont["titulo"])
    rr.bold = True
    rr.font.size = Pt(13)
    s = d.add_paragraph(cont["subtitulo"])
    s.alignment = WD_ALIGN_PARAGRAPH.CENTER

    for bl in cont["bloques"]:
        tipo = bl[0]
        if tipo == "titulo":
            d.add_heading(bl[1], level=2)
        elif tipo == "subtitulo":
            d.add_heading(bl[1], level=3)
        elif tipo == "parrafo":
            d.add_paragraph(bl[1])
        elif tipo == "nota":
            n = d.add_paragraph().add_run(bl[1])
            n.italic = True
            n.font.size = Pt(8.5)
            n.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
        elif tipo == "lista":
            for it in bl[1]:
                d.add_paragraph(str(it), style="List Bullet")
        elif tipo == "tabla":
            enc_t, filas, col_color = bl[1], bl[2], bl[3]
            tb = d.add_table(rows=1, cols=len(enc_t))
            tb.style = "Table Grid"
            for c, txt in zip(tb.rows[0].cells, enc_t):
                c.text = txt
                c.paragraphs[0].runs[0].bold = True
                _sombrear(c, "D9E2F3")
            for f in filas:
                cells = tb.add_row().cells
                for j, txt in enumerate(f):
                    cells[j].text = str(txt)
                    for pp in cells[j].paragraphs:
                        for run in pp.runs:
                            run.font.size = Pt(9)
                    if col_color is not None and j == col_color and str(txt) in COLORES:
                        _sombrear(cells[j], COLORES[str(txt)])
            d.add_paragraph()

    d.add_paragraph()
    firmas = pl.get("firmas", [])
    if firmas:
        tf = d.add_table(rows=1, cols=len(firmas))
        for c, f in zip(tf.rows[0].cells, firmas):
            c.text = ""
            p = c.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run("\n\n______________________________\n")
            p.add_run(f.get("nombre", "")).bold = True
            p.add_run(f"\n{f.get('cargo', '')}" + (f"\n{f['matricula']}" if f.get("matricula") else ""))
    d.save(ruta)
    return Path(ruta)


# ----------------------------------------------------------------- PDF
def a_pdf(cont: dict, ruta: Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape

    pl = plantilla()
    est = getSampleStyleSheet()
    normal = ParagraphStyle("n", parent=est["Normal"], fontName="Helvetica", fontSize=9.5, leading=12.5)
    celda = ParagraphStyle("c", parent=normal, fontSize=8, leading=10)
    h2 = ParagraphStyle("h2", parent=est["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4)
    h3 = ParagraphStyle("h3", parent=est["Heading3"], fontSize=10.5, spaceBefore=6, spaceAfter=3)
    tit = ParagraphStyle("t", parent=est["Title"], fontSize=13.5, alignment=TA_CENTER)
    nota = ParagraphStyle("nota", parent=normal, fontSize=8, textColor=colors.HexColor("#555555"), fontName="Helvetica-Oblique")
    ancho = letter[0] - 4.4 * cm
    logo = _ruta_logo(pl)

    def encabezado(canvas, doc):
        canvas.saveState()
        y = letter[1] - 1.6 * cm
        if logo:
            canvas.drawImage(str(logo), 2.2 * cm, y - 0.9 * cm, width=2.6 * cm, height=1.5 * cm, preserveAspectRatio=True, mask="auto")
        else:
            canvas.setFont("Helvetica", 8)
            canvas.drawString(2.2 * cm, y - 0.3 * cm, "[LOGO]")
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawCentredString(letter[0] / 2, y, pl.get("entidad", ""))
        canvas.setFont("Helvetica", 9)
        canvas.drawCentredString(letter[0] / 2, y - 0.45 * cm, pl.get("dependencia", ""))
        canvas.setFont("Helvetica", 7.5)
        canvas.drawRightString(letter[0] - 2.2 * cm, y, f"Código: {pl.get('codigo_formato', '')}")
        canvas.drawRightString(letter[0] - 2.2 * cm, y - 0.35 * cm, f"Versión: {pl.get('version_formato', '')}")
        canvas.drawRightString(letter[0] - 2.2 * cm, y - 0.7 * cm, f"Página {doc.page}")
        canvas.line(2.2 * cm, y - 1.1 * cm, letter[0] - 2.2 * cm, y - 1.1 * cm)
        canvas.setFont("Helvetica", 7)
        canvas.drawCentredString(letter[0] / 2, 1.2 * cm, f"{pl.get('direccion', '')} · {pl.get('telefono', '')} · {pl.get('correo', '')}")
        canvas.drawCentredString(letter[0] / 2, 0.85 * cm, pl.get("pie", "")[:150])
        canvas.restoreState()

    def P_(t, s=normal):
        return Paragraph(escape(str(t)).replace("\n", "<br/>"), s)

    flujo = [P_(cont["titulo"], tit), P_(cont["subtitulo"], ParagraphStyle("st", parent=normal, alignment=TA_CENTER)), Spacer(1, 8)]
    for bl in cont["bloques"]:
        tipo = bl[0]
        if tipo == "titulo":
            flujo.append(P_(bl[1], h2))
        elif tipo == "subtitulo":
            flujo.append(P_(bl[1], h3))
        elif tipo == "parrafo":
            flujo += [P_(bl[1]), Spacer(1, 4)]
        elif tipo == "nota":
            flujo += [Spacer(1, 6), P_(bl[1], nota)]
        elif tipo == "lista":
            flujo.append(ListFlowable([ListItem(P_(x), leftIndent=12) for x in bl[1]], bulletType="bullet", start="•"))
        elif tipo == "tabla":
            enc_t, filas, col_color = bl[1], bl[2], bl[3]
            datos = [[P_(x, ParagraphStyle("hh", parent=celda, fontName="Helvetica-Bold")) for x in enc_t]] + \
                    [[P_(x, celda) for x in f] for f in filas]
            n = len(enc_t)
            pesos = ANCHOS.get(tuple(enc_t)) or {2: [0.4, 0.6], 3: [0.45, 0.2, 0.35], 4: [0.25, 0.13, 0.37, 0.25],
                                                 5: [0.15, 0.22, 0.11, 0.3, 0.22]}.get(n, [1 / n] * n)
            t = Table(datos, colWidths=[ancho * p for p in pesos], repeatRows=1)
            estilo = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
                      ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3")), ("VALIGN", (0, 0), (-1, -1), "TOP")]
            if col_color is not None:
                for i, f in enumerate(filas, start=1):
                    c = COLORES.get(str(f[col_color]))
                    if c:
                        estilo.append(("BACKGROUND", (col_color, i), (col_color, i), colors.HexColor("#" + c)))
            t.setStyle(TableStyle(estilo))
            flujo += [t, Spacer(1, 8)]
    firmas = pl.get("firmas", [])
    if firmas:
        celdas = [P_(f"<br/><br/>______________________________<br/><b>{escape(f.get('nombre', ''))}</b><br/>{escape(f.get('cargo', ''))}"
                     + (f"<br/>{escape(f['matricula'])}" if f.get("matricula") else ""),
                     ParagraphStyle("f", parent=normal, alignment=TA_CENTER)) for f in firmas]
        # P_ escapa el texto: aquí se construye el Paragraph directo para conservar <b> y <br/>
        celdas = [Paragraph(f"<br/><br/>______________________________<br/><b>{escape(f.get('nombre', ''))}</b><br/>"
                            f"{escape(f.get('cargo', ''))}" + (f"<br/>{escape(f['matricula'])}" if f.get("matricula") else ""),
                            ParagraphStyle("f", parent=normal, alignment=TA_CENTER)) for f in firmas]
        flujo += [Spacer(1, 20), Table([celdas], colWidths=[ancho / len(firmas)] * len(firmas))]
    doc = SimpleDocTemplate(str(ruta), pagesize=letter, leftMargin=2.2 * cm, rightMargin=2.2 * cm,
                            topMargin=3.2 * cm, bottomMargin=2.0 * cm, title=cont["titulo"], author=pl.get("entidad", ""))
    doc.build(flujo, onFirstPage=encabezado, onLaterPages=encabezado)
    return Path(ruta)


def word_a_pdf_libreoffice(docx_ruta: Path) -> Path | None:
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    for cand in (r"C:\Program Files\LibreOffice\program\soffice.exe", r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"):
        if not exe and Path(cand).exists():
            exe = cand
    if not exe:
        return None
    subprocess.run([exe, "--headless", "--convert-to", "pdf", "--outdir", str(Path(docx_ruta).parent), str(docx_ruta)],
                   capture_output=True, timeout=180)
    pdf = Path(docx_ruta).with_suffix(".pdf")
    return pdf if pdf.exists() else None


# ------------------------------------------------------------ generar y guardar
def generar(tramite_id: int, tipo: str, usuario: str, conclusion: str = "", observaciones_extra: str = "",
            pdf_desde_word: bool = False, carpeta: Path | None = None) -> dict:
    cont = contenido_acta(tramite_id, observaciones_extra) if tipo == "acta_observaciones" else \
        contenido_informe(tramite_id, conclusion, observaciones_extra)
    exp = cont["expediente"]
    from core import documentos as Dm
    carpeta = carpeta or (Dm.EXPEDIENTES_DIR / Dm._seguro(exp["radicado"]) / f"{tramite_id}_{cont['tramite']['tipo']}" / "informes")
    carpeta.mkdir(parents=True, exist_ok=True)
    base = f"{tipo}_{Dm._seguro(exp['radicado'])}_{date.today().isoformat()}"
    docx_r = a_word(cont, carpeta / f"{base}.docx")
    pdf_r = word_a_pdf_libreoffice(docx_r) if pdf_desde_word else None
    if pdf_r is None:
        pdf_r = a_pdf(cont, carpeta / f"{base}.pdf")
    iid = db.ejecutar("INSERT INTO informes (tramite_id, tipo, archivo_docx, archivo_pdf, conclusion, usuario) VALUES (?,?,?,?,?,?)",
                      (tramite_id, tipo, str(docx_r), str(pdf_r), conclusion or cont.get("conclusion_sugerida", ""), usuario))
    auditoria.registrar(usuario, "crear", "informe", iid, despues={"tramite_id": tramite_id, "tipo": tipo,
                                                                    "docx": str(docx_r), "pdf": str(pdf_r)})
    return {"id": iid, "docx": docx_r, "pdf": pdf_r, "contenido": cont}


def listar(tramite_id: int) -> list[dict]:
    return db.consultar("SELECT * FROM informes WHERE tramite_id=? ORDER BY id DESC", (tramite_id,))
