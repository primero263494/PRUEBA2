"""Streamlit simulado para probar que cada página se dibuja sin errores.

No reemplaza ver la página: solo ejecuta su código con respuestas por defecto
de cada control (primera opción, valor inicial, botones sin presionar), para
detectar errores como KeyError o TypeError antes de abrir la aplicación.
"""
import sys
import types
from contextlib import contextmanager


class _Estado(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(k) from e

    def __setattr__(self, k, v):
        self[k] = v


class _Bloque:
    """Contenedor (columna, pestaña, expander, form…): admite `with` y todos los controles."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, nombre):
        return getattr(st, nombre)


def _opciones(options):
    return list(options) if options is not None else []


def _selectbox(label, options, index=0, format_func=str, key=None, **kw):
    ops = _opciones(options)
    if key and key in st.session_state and st.session_state[key] in ops:
        return st.session_state[key]
    for o in ops:
        format_func(o)
    v = ops[index] if ops and index is not None and index < len(ops) else None
    if key:
        st.session_state[key] = v
    return v


def _valor(label=None, value=None, *a, key=None, **kw):
    if key and key in st.session_state:
        return st.session_state[key]
    if key:
        st.session_state[key] = value
    return value


def _numero(label, min_value=None, max_value=None, value=None, step=None, key=None, **kw):
    v = value if value is not None else (min_value if min_value is not None else 0)
    if key:
        st.session_state.setdefault(key, v)
        return st.session_state[key]
    return v


def _columns(spec, **kw):
    n = spec if isinstance(spec, int) else len(spec)
    return [_Bloque() for _ in range(n)]


def _tabs(nombres):
    return [_Bloque() for _ in nombres]


def _nada(*a, **kw):
    return None


def _falso(*a, **kw):
    return False


def _data_editor(data, *a, **kw):
    return data


def _multiselect(label, options, default=None, **kw):
    return list(default or [])


def _date_input(label, value=None, **kw):
    import datetime
    if isinstance(value, datetime.date) or value is None:
        return value
    return value


@contextmanager
def _ctx(*a, **kw):
    yield _Bloque()


class _ColumnConfig:
    def __getattr__(self, n):
        return lambda *a, **kw: None


st = types.ModuleType("streamlit")
st.session_state = _Estado()
st.query_params = _Estado()
st.column_config = _ColumnConfig()
for nombre in ("title", "header", "subheader", "markdown", "write", "caption", "info", "warning", "error", "success",
               "dataframe", "table", "json", "metric", "image", "code", "divider", "text", "latex", "plotly_chart",
               "map", "download_button", "set_page_config", "toast", "rerun", "stop", "html", "pdf"):
    setattr(st, nombre, _nada)
st.selectbox = _selectbox
st.radio = _selectbox
st.segmented_control = _selectbox
st.text_input = lambda label, value="", *a, key=None, **kw: _valor(label, value, key=key)
st.text_area = lambda label, value="", *a, key=None, **kw: _valor(label, value, key=key)
st.number_input = _numero
st.slider = _numero
st.checkbox = lambda label, value=False, *a, key=None, **kw: _valor(label, value, key=key)
st.toggle = st.checkbox
st.button = _falso
st.form_submit_button = _falso
st.file_uploader = _nada
st.data_editor = _data_editor
st.multiselect = _multiselect
st.date_input = _date_input
st.columns = _columns
st.tabs = _tabs
st.expander = _ctx
st.container = _ctx
st.form = _ctx
st.popover = _ctx
st.spinner = _ctx
st.sidebar = _Bloque()
st.progress = _nada


def _desconocido(nombre):
    if nombre.startswith("__"):
        raise AttributeError(nombre)
    return _nada


st.__getattr__ = _desconocido     # cualquier otro elemento de solo presentación


def instalar():
    sys.modules["streamlit"] = st
    return st
