"""Pruebas del análisis de planos y del módulo 7 (informes)."""
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import ajustes  # noqa: E402

_TMP = Path(tempfile.mkdtemp())
RUTA_BD = lambda: _TMP / "prueba.db"
ajustes.ruta_bd = RUTA_BD

from core import calculadoras, chequeo, db, documentos as D, expedientes as E, informes  # noqa: E402
from core.planos import analisis as A, lectores  # noqa: E402

EJ = Path(__file__).parent / "ejemplos"


@pytest.fixture(scope="module")
def tramite():
    D.EXPEDIENTES_DIR = _TMP / "exp"
    D.PAPELERA = _TMP / "pap"
    db.migrar(); E.migrar(); D.migrar(); chequeo.migrar(); calculadoras.migrar(); A.migrar(); informes.migrar()
    eid = E.crear(dict(solicitante="Ana Pérez", poligono="S1-CN-1", clase_suelo="urbano", direccion="Cra 30 # 31-20"), "prueba")
    tid = E.agregar_tramite(eid, "construccion_urbana", "obra_nueva", {"area_lote": 200, "n_pisos": 3}, "prueba")
    return eid, tid


@pytest.fixture(scope="module")
def lecturas():
    return [lectores.analizar(f) for f in sorted(EJ.iterdir()) if f.is_file()]


def _por_item(res, texto):
    return [i for i in res["items"] if texto in i["item"]]


def test_lectura_niveles(lecturas):
    niveles = {r["archivo"]: r["nivel"] for r in lecturas}
    assert niveles["arquitectonico.dxf"] == "completa"
    assert niveles["modelo.ifc"] == "completa"
    assert niveles["memoria_estructural.pdf"] == "texto"


def test_cruces_detectan_inconsistencias(tramite, lecturas):
    eid, tid = tramite
    res = A.evaluar(lecturas, E.obtener(eid), E.tramite(tid))
    assert _por_item(res, "Perfil de suelo: memoria")[0]["estado"] == "NO CUMPLE"       # C vs D
    assert _por_item(res, "Área construida: coherencia")[0]["estado"] == "NO CUMPLE"    # 460 vs 470
    assert _por_item(res, "Deriva máxima")[0]["estado"] == "CUMPLE"
    assert _por_item(res, "Número de sondeos")[0]["estado"] == "CUMPLE"
    assert _por_item(res, "Alturas de entrepiso")[0]["estado"] == "CUMPLE"
    assert all(i["norma"] for i in res["items"] if i["estado"] in ("CUMPLE", "NO CUMPLE"))
    assert res["concepto"]["sugerido"].startswith("NO VIABLE")


def test_correccion_del_revisor_cambia_concepto(tramite, lecturas):
    eid, tid = tramite
    corr = [dict(r, datos=dict(r["datos"])) for r in lecturas]
    for r in corr:
        if r["disciplina"] == "geotecnico" and "perfil_suelo" in r["datos"]:
            r["datos"]["perfil_suelo"] = {"valor": "D", "unidad": "", "evidencia": "Corregido"}
        if "area_construida_texto" in r["datos"]:
            r["datos"]["area_construida_texto"] = {"valor": 460.0, "unidad": "m²", "evidencia": "Corregido"}
    res = A.evaluar(corr, E.obtener(eid), E.tramite(tid))
    assert not [i for i in res["items"] if i["estado"] == "NO CUMPLE"]


def test_guardar_y_ultimo(tramite, lecturas):
    eid, tid = tramite
    res = A.evaluar(lecturas, E.obtener(eid), E.tramite(tid))
    A.guardar(tid, lecturas, res, "prueba")
    assert A.ultimo(tid)["concepto"]["sugerido"] == res["concepto"]["sugerido"]


def test_informe_word_y_pdf(tramite):
    eid, tid = tramite
    r = calculadoras.indices(200, 160, [160, 160, 140], 0, "S1-CN-1")
    calculadoras.guardar(tid, "indices", {}, r, "prueba")
    out = informes.generar(tid, "informe_tecnico", "prueba", carpeta=_TMP / "inf")
    assert out["docx"].exists() and out["pdf"].exists()
    import docx
    texto = "\n".join(p.text for p in docx.Document(out["docx"]).paragraphs)
    assert "Verificación normativa" in texto and "Conclusión" in texto
    assert "NO es viable" in texto            # hay NO CUMPLE en el análisis de planos
    assert out["pdf"].read_bytes()[:4] == b"%PDF"
    assert informes.listar(tid)


def test_acta_cita_plazo(tramite):
    eid, tid = tramite
    out = informes.generar(tid, "acta_observaciones", "prueba", observaciones_extra="Aportar paz y salvo predial",
                           carpeta=_TMP / "inf")
    import docx
    texto = "\n".join(p.text for p in docx.Document(out["docx"]).paragraphs)
    assert "30 días hábiles" in texto and "2.2.6.1.2.2.4" in texto
    assert "Aportar paz y salvo predial" in texto


def test_plantilla_y_logo(tmp_path, monkeypatch):
    monkeypatch.setattr(informes, "PLANTILLAS", tmp_path)
    monkeypatch.setattr(informes, "PLANTILLA", tmp_path / "plantilla.yaml")
    (tmp_path / "plantilla.yaml").write_text("entidad: X\nfirmas: []\n", encoding="utf-8")
    from PIL import Image
    Image.new("RGB", (60, 30), "green").save(tmp_path / "l.png")
    informes.guardar_logo(tmp_path / "l.png", "prueba")
    assert informes.plantilla()["logo"] == "logo.png"
    with pytest.raises(ValueError):
        informes.guardar_logo(tmp_path / "plantilla.yaml", "prueba")
