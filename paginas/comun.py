"""Utilidades compartidas por las páginas de Streamlit."""
import tempfile
from pathlib import Path

import streamlit as st

from core import auth


def usuario() -> dict:
    return st.session_state.get("usuario") or {}


def puede(permiso: str) -> bool:
    u = usuario()
    return bool(u) and auth.puede(u["rol"], permiso)


def exigir(permiso: str) -> bool:
    if not puede(permiso):
        st.warning("Su rol no tiene permiso para esta acción.")
        return False
    return True


def guardar_subidos(subidos) -> list[Path]:
    """Guarda archivos de st.file_uploader en una carpeta temporal y devuelve rutas."""
    if not subidos:
        return []
    if not isinstance(subidos, list):
        subidos = [subidos]
    carpeta = Path(tempfile.mkdtemp(prefix="subida_"))
    rutas = []
    for s in subidos:
        r = carpeta / s.name
        r.write_bytes(s.getbuffer())
        rutas.append(r)
    return rutas


def confirmar_eliminacion(clave: str, descripcion: str) -> str | None:
    """Doble confirmación + motivo. Devuelve el motivo si el usuario confirma."""
    with st.expander(f"Eliminar {descripcion}"):
        st.caption("La eliminación queda registrada con su usuario, la fecha y el motivo.")
        motivo = st.text_input("Motivo de la eliminación", key=f"motivo_{clave}")
        seguro = st.checkbox(f"Confirmo que deseo eliminar {descripcion}", key=f"conf_{clave}")
        if st.button("Eliminar definitivamente", key=f"btn_{clave}", type="primary",
                     disabled=not (seguro and len(motivo.strip()) >= 5)):
            return motivo.strip()
    return None


def cita(texto: str) -> None:
    if texto:
        st.caption(f"Fuente: {texto}")


def campo_fecha(contenedor, etiqueta: str, valor=None, key: str | None = None, obligatorio: bool = False,
                ayuda: str | None = None):
    """Campo de fecha con calendario. Devuelve 'AAAA-MM-DD' o None.

    `valor` puede ser date o texto ISO. Sin valor, el campo queda vacío (salvo
    que sea obligatorio, que arranca en hoy). Admite fechas desde 1900, para
    obras antiguas (reconocimientos)."""
    from datetime import date
    if isinstance(valor, str) and valor.strip():
        try:
            valor = date.fromisoformat(valor.strip()[:10])
        except ValueError:
            valor = None
    elif not isinstance(valor, date):
        valor = None
    if valor is None and obligatorio:
        valor = date.today()
    v = contenedor.date_input(etiqueta, value=valor, min_value=date(1900, 1, 1), max_value=date(2100, 12, 31),
                              format="DD/MM/YYYY", key=key, help=ayuda)
    return v.isoformat() if v else None


def indice_foco(ids: list, clave: str = "tramite_foco") -> int:
    """Índice del trámite elegido desde Inicio (si está en la lista); si no, el primero."""
    foco = st.session_state.get(clave)
    return ids.index(foco) if foco in ids else 0
