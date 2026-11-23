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
