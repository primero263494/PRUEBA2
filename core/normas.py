"""Carga de normas (PDF, Word, texto, escaneos) para consulta y análisis.

Cada norma cargada se guarda en datos/normas/<id>/, se extrae su texto
(digital, OCR local o IA según Configuración) y se divide en artículos para
el buscador y para que el módulo de análisis de planos la cite.
"""
from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path

from core import auditoria, db, lectura
from core.rutas import NORMAS_DIR

AMBITOS = ("nacional", "municipal", "ambiental", "tecnica")
DISCIPLINAS = ("urbanistica", "estructural", "geotecnica", "ambiental", "tributaria", "otra")

# "ARTÍCULO 2.2.6.1.2.3.1", "Artículo 138.", "ART. 19", "H.3.2.3 —" (NSR-10)
_PATRON_ARTICULO = re.compile(
    r"^\s*(?:ART[ÍI]CULO|Art[íi]culo|ART\.)\s+([0-9][0-9A-Za-z\.\-º°]*)\s*[\.\:\-–]?\s*(.*)$"
    r"|^\s*([A-K]\.\d+(?:\.\d+){1,4})\s+[—\-–]\s*(.*)$",
    re.MULTILINE,
)


def dividir_articulos(texto: str) -> list[dict]:
    marcas = list(_PATRON_ARTICULO.finditer(texto))
    salida = []
    for i, m in enumerate(marcas):
        num = (m.group(1) or m.group(3) or "").rstrip(".-–:º° ")
        titulo = (m.group(2) or m.group(4) or "").strip()[:200]
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        cuerpo = texto[m.start():fin].strip()
        if num:
            salida.append({"articulo": num, "titulo": titulo, "texto": cuerpo})
    return salida


def cargar(archivo_origen: Path, nombre: str, ambito: str, disciplina: str,
           version: str, usuario: str, forzar_modo: str | None = None) -> dict:
    if ambito not in AMBITOS:
        raise ValueError(f"Ámbito no válido: {ambito}")
    nid = db.ejecutar(
        "INSERT INTO normas (nombre, ambito, disciplina, version, archivo, cargado_por, verificado)"
        " VALUES (?,?,?,?,?,?,?)",
        (nombre, ambito, disciplina, version, "", usuario, date.today().isoformat()),
    )
    carpeta = NORMAS_DIR / str(nid)
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / Path(archivo_origen).name
    shutil.copy2(archivo_origen, destino)

    res = lectura.leer(destino, forzar_modo=forzar_modo)
    ruta_txt = carpeta / "texto.txt"
    ruta_txt.write_text(res["texto"], encoding="utf-8")
    articulos = dividir_articulos(res["texto"])
    with db.conexion() as con:
        con.execute("UPDATE normas SET archivo=?, texto=?, paginas=?, metodo_lectura=? WHERE id=?",
                    (str(destino), str(ruta_txt), res["paginas"], res["metodo"], nid))
        con.executemany(
            "INSERT INTO normas_articulos (norma_id, articulo, titulo, texto) VALUES (?,?,?,?)",
            [(nid, a["articulo"], a["titulo"], a["texto"]) for a in articulos],
        )
    auditoria.registrar(usuario, "cargar", "norma", nid,
                        despues={"nombre": nombre, "ambito": ambito, "disciplina": disciplina,
                                 "version": version, "metodo": res["metodo"], "articulos": len(articulos)})
    return {"id": nid, "articulos": len(articulos), "metodo": res["metodo"], "aviso": res["aviso"],
            "caracteres": len(res["texto"])}


def listar() -> list[dict]:
    return db.consultar(
        "SELECT n.*, (SELECT COUNT(*) FROM normas_articulos a WHERE a.norma_id=n.id) AS n_articulos "
        "FROM normas n ORDER BY ambito, nombre")


def buscar(texto: str, norma_id: int | None = None, limite: int = 50) -> list[dict]:
    """Búsqueda simple por palabra clave o número de artículo."""
    patron = f"%{texto.strip()}%"
    sql = ("SELECT a.id, a.norma_id, n.nombre AS norma, a.articulo, a.titulo, a.texto "
           "FROM normas_articulos a JOIN normas n ON n.id=a.norma_id "
           "WHERE n.vigente=1 AND (a.texto LIKE ? OR a.articulo = ?)")
    params: list = [patron, texto.strip()]
    if norma_id:
        sql += " AND a.norma_id=?"
        params.append(norma_id)
    sql += " ORDER BY (a.articulo = ?) DESC, a.norma_id, a.id LIMIT ?"
    params.extend([texto.strip(), limite])
    return db.consultar(sql, params)


def marcar_verificada(nid: int, usuario: str, vigente: bool = True, nota: str = "") -> None:
    hoy = date.today().isoformat()
    db.ejecutar("UPDATE normas SET verificado=?, vigente=? WHERE id=?", (hoy, 1 if vigente else 0, nid))
    auditoria.registrar(usuario, "verificar", "norma", nid,
                        despues={"verificado": hoy, "vigente": vigente}, motivo=nota)


def eliminar(nid: int, usuario: str, motivo: str) -> None:
    """Elimina una norma cargada (la página pide confirmación antes)."""
    fila = db.consultar("SELECT * FROM normas WHERE id=?", (nid,))
    if not fila:
        return
    db.ejecutar("DELETE FROM normas WHERE id=?", (nid,))
    shutil.rmtree(NORMAS_DIR / str(nid), ignore_errors=True)
    auditoria.registrar(usuario, "eliminar", "norma", nid, antes=fila[0], motivo=motivo)
