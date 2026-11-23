"""Lectura de texto de documentos y escaneos, con dos modos elegibles:

* local: OCR en el equipo (Tesseract en español). Funciona sin internet.
* ia:    modelo de visión por API (requiere internet y clave en variable de
         entorno). Lee mejor cuadros de áreas y rótulos escaneados, pero el
         archivo sale del equipo hacia el proveedor.
* auto:  usa IA si hay internet y clave; si no, cae a local sin error.

El modo se elige en Configuración (config/ajustes.yaml -> lectura_escaneos).
"""
from __future__ import annotations

import base64
import os
import shutil
import socket
import subprocess
from pathlib import Path

from core import ajustes
from core.rutas import TEMP_DIR

EXT_IMAGEN = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


# ----------------------------------------------------------------- utilidades
def hay_internet(host: str = "api.anthropic.com", puerto: int = 443, espera: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, puerto), timeout=espera):
            return True
    except OSError:
        return False


def ia_disponible() -> tuple[bool, str]:
    var = ajustes.obtener("lectura_escaneos.ia_variable_clave", "ANTHROPIC_API_KEY")
    if not os.environ.get(var):
        return False, f"No hay clave en la variable de entorno {var}."
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False, "Falta la librería 'anthropic' (pip install anthropic)."
    if not hay_internet():
        return False, "Sin conexión a internet."
    return True, "IA disponible."


def modo_efectivo() -> tuple[str, str]:
    """Devuelve (modo, explicación) después de resolver 'auto'."""
    modo = ajustes.obtener("lectura_escaneos.modo", "auto")
    if modo == "local":
        return "local", "Modo local elegido en Configuración."
    ok, msg = ia_disponible()
    if modo == "ia":
        return ("ia", msg) if ok else ("local", f"Se pidió IA pero no está disponible ({msg}). Se usa OCR local.")
    return ("ia", "Automático: " + msg) if ok else ("local", f"Automático: {msg} Se usa OCR local.")


# ------------------------------------------------------------- texto digital
def texto_pdf_digital(ruta: Path) -> tuple[str, int]:
    """Texto embebido del PDF (sin OCR). Devuelve (texto, páginas)."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(ruta)
        return "\n".join(p.get_text() for p in doc), doc.page_count
    except ImportError:
        pass
    if shutil.which("pdftotext"):
        out = subprocess.run(["pdftotext", "-layout", str(ruta), "-"], capture_output=True, text=True)
        paginas = out.stdout.count("\f") or None
        return out.stdout, paginas or 0
    return "", 0


def _pdf_a_imagenes(ruta: Path, dpi: int = 200) -> list[Path]:
    destino = TEMP_DIR / f"ocr_{ruta.stem}"
    destino.mkdir(parents=True, exist_ok=True)
    try:
        import fitz
        doc = fitz.open(ruta)
        salida = []
        for i, pag in enumerate(doc):
            img = destino / f"p{i + 1:04d}.png"
            pag.get_pixmap(dpi=dpi).save(img)
            salida.append(img)
        return salida
    except ImportError:
        pass
    if shutil.which("pdftoppm"):
        subprocess.run(["pdftoppm", "-r", str(dpi), "-gray", "-png", str(ruta), str(destino / "p")], check=True)
        return sorted(destino.glob("p*.png"))
    raise RuntimeError("No hay cómo convertir el PDF en imágenes: instale PyMuPDF (pip install pymupdf).")


# ------------------------------------------------------------------ OCR local
def ocr_local(imagen: Path) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:
        raise RuntimeError("Falta pytesseract/Pillow para OCR local.") from e
    idioma = ajustes.obtener("lectura_escaneos.idioma_ocr", "spa")
    return pytesseract.image_to_string(Image.open(imagen), lang=idioma)


# -------------------------------------------------------------------- OCR IA
PROMPT_TRANSCRIBIR = (
    "Transcribe fielmente todo el texto legible de esta imagen (plano o documento "
    "de un trámite urbanístico en Colombia). Conserva cifras, unidades, cotas y "
    "tablas (como tablas Markdown). No inventes nada: marca [ilegible] donde no se lea."
)


def ocr_ia(imagen: Path, instruccion: str = PROMPT_TRANSCRIBIR) -> str:
    import anthropic
    modelo = ajustes.obtener("lectura_escaneos.ia_modelo", "claude-sonnet-5-5")
    espera = ajustes.obtener("lectura_escaneos.ia_tiempo_espera_s", 60)
    tipo = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(imagen.suffix.lower().strip("."), None)
    ruta = imagen
    if tipo is None:  # TIFF/BMP -> PNG
        from PIL import Image
        ruta = TEMP_DIR / (imagen.stem + ".png")
        Image.open(imagen).save(ruta)
        tipo = "png"
    datos = base64.standard_b64encode(ruta.read_bytes()).decode()
    cliente = anthropic.Anthropic(timeout=espera)
    resp = cliente.messages.create(
        model=modelo, max_tokens=4096,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": f"image/{tipo}", "data": datos}},
            {"type": "text", "text": instruccion},
        ]}],
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


# ---------------------------------------------------------- punto de entrada
def leer(ruta: Path, forzar_modo: str | None = None) -> dict:
    """Lee cualquier PDF, imagen, Word o texto. Devuelve
    {texto, paginas, metodo, aviso}. Si el PDF trae texto digital, no usa OCR."""
    ruta = Path(ruta)
    ext = ruta.suffix.lower()
    if ext in {".txt", ".md", ".csv"}:
        return {"texto": ruta.read_text(encoding="utf-8", errors="replace"), "paginas": None,
                "metodo": "texto_digital", "aviso": ""}
    if ext == ".docx":
        import docx
        d = docx.Document(ruta)
        return {"texto": "\n".join(p.text for p in d.paragraphs), "paginas": None,
                "metodo": "texto_digital", "aviso": ""}

    modo, aviso = (forzar_modo, "Modo forzado.") if forzar_modo else modo_efectivo()
    if ext == ".pdf":
        texto, paginas = texto_pdf_digital(ruta)
        if len(texto.strip()) / max(paginas, 1) > 40:  # más de 40 caracteres por página: texto real
            return {"texto": texto, "paginas": paginas, "metodo": "texto_digital", "aviso": ""}
        imagenes = _pdf_a_imagenes(ruta)
    elif ext in EXT_IMAGEN:
        imagenes = [ruta]
    else:
        return {"texto": "", "paginas": None, "metodo": "sin_texto",
                "aviso": f"Formato {ext} sin lectura de texto."}

    partes = []
    for img in imagenes:
        if modo == "ia":
            try:
                partes.append(ocr_ia(img))
                continue
            except Exception as e:  # caída de red a mitad del proceso
                aviso += f" Falló IA en {img.name} ({e}); se usó OCR local."
        partes.append(ocr_local(img))
    metodo = "ia" if modo == "ia" and "Falló IA" not in aviso else "ocr_local"
    return {"texto": "\n\n".join(partes), "paginas": len(imagenes), "metodo": metodo, "aviso": aviso.strip()}
