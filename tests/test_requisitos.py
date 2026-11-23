"""Pruebas del listado de requisitos de la Secretaría, paquete completo y carga desde la lista de chequeo."""
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import ajustes  # noqa: E402

_tmpdir = Path(tempfile.mkdtemp())
RUTA_BD = lambda: _tmpdir / "requisitos.db"  # noqa: E731
ajustes.ruta_bd = RUTA_BD

from core import chequeo as C, db, documentos as D, expedientes as E, verificacion as V  # noqa: E402
from core import parametros as P  # noqa: E402

HOY = date.today()


def _tr(tipo, modalidad, clase="urbano", persona="natural", **datos):
    eid = E.crear(dict(solicitante="Ana", clase_suelo=clase, tipo_persona=persona, poligono="S1-CN-1"), "f")
    tid = E.agregar_tramite(eid, tipo, modalidad, datos, "f", HOY.isoformat())
    return E.obtener(eid), E.tramite(tid)


def _arch(nombre):
    r = _tmpdir / nombre
    r.write_bytes(b"%PDF-1.4 prueba " + nombre.encode())
    return r


def _claves(exp, tr):
    return [r["tipo"] for r in D.requisitos(exp, tr)]


def test_todas_las_listas_usan_documentos_y_tramites_validos():
    cat = D.catalogo()
    tipos = E.tipos()
    for clave, l in P.valor("requisitos.listas").items():
        assert all(t in tipos for t in l["tipos"]), clave
        for r in l["requisitos"]:
            assert all(o in cat for o in r["doc"].split("|")), (clave, r["doc"])


def test_urbana_estudio_o_apique_por_pisos():
    exp, tr = _tr("construccion_urbana", "obra_nueva", n_pisos=4)
    assert "estudio_suelos" in _claves(exp, tr) and "apique" not in _claves(exp, tr)
    exp, tr = _tr("construccion_urbana", "obra_nueva", n_pisos=2)
    assert "apique" in _claves(exp, tr)
    exp, tr = _tr("construccion_urbana", "obra_nueva")
    assert "estudio_suelos|apique" in _claves(exp, tr)


def test_rural_estudio_por_area_mansarda_o_parcelacion():
    base = dict(tipo="construccion_rural", modalidad="obra_nueva", clase="rural")
    exp, tr = _tr(**base, n_pisos=2, area_construida=180)
    assert "apique" in _claves(exp, tr)
    exp, tr = _tr(**base, n_pisos=1, area_construida=320)
    assert "estudio_suelos" in _claves(exp, tr)
    exp, tr = _tr(**base, n_pisos=2, area_construida=150, mansarda=True)
    assert "estudio_suelos" in _claves(exp, tr)
    exp, tr = _tr(**base, n_pisos=1, area_construida=100, en_parcelacion=True)
    c = _claves(exp, tr)
    assert "estudio_suelos" in c and "aprobacion_parcelacion" in c


def test_condicionales():
    exp, tr = _tr("construccion_urbana", "obra_nueva", persona="juridica", n_pisos=3, propiedad_horizontal=True,
                  apoderado=True)
    c = _claves(exp, tr)
    assert {"camara_comercio", "autorizacion_copropiedad", "poder"} <= set(c)
    exp, tr = _tr("construccion_urbana", "obra_nueva", n_pisos=3)
    assert not {"camara_comercio", "autorizacion_copropiedad", "poder"} & set(_claves(exp, tr))


def test_listas_por_clase_y_modalidad():
    exp, tr = _tr("reconocimiento", "rural", clase="rural")
    assert "ubicacion_pozo_septico" in _claves(exp, tr)
    exp, tr = _tr("reconocimiento", "urbano", clase="urbano")
    assert "ubicacion_pozo_septico" not in _claves(exp, tr) and "informe_alineamiento" in _claves(exp, tr)
    exp, tr = _tr("adicion_modificacion_cambio_uso", "cambio_de_uso")
    assert "planos_estructurales" not in _claves(exp, tr)
    exp, tr = _tr("adicion_modificacion_cambio_uso", "ampliacion")
    assert "planos_estructurales" in _claves(exp, tr)


def test_tramites_nuevos_del_listado():
    for tipo, doc in (("desenglobe", "pago_nomenclatura"), ("reclamo_estrato", "impuesto_predial"),
                      ("publicidad_exterior", "formato_publicidad"), ("apertura_vanos", "visita_tecnica"),
                      ("inscripcion_profesionales", "formato_inscripcion_profesionales"),
                      ("nomenclatura_dian", "certificado_catastro")):
        exp, tr = _tr(tipo, E.tipos()[tipo]["modalidades"][0])
        assert doc in _claves(exp, tr), tipo
    exp, tr = _tr("estrato", "certificado", clase="rural")
    assert "pago_nomenclatura" not in _claves(exp, tr)


def test_opcional_no_bloquea_verificacion():
    exp, tr = _tr("permiso_ventas", "radicacion")
    for r in D.requeridos(exp, tr):
        D.subir(_arch(f"{r}.pdf"), exp["id"], tr["id"], r.split("|")[0], "f",
                fecha_expedicion=HOY.isoformat())
    res = {r["item"]: r["estado"] for r in V.verificar(exp, E.tramite(tr["id"]))}
    assert res["Documentos exigidos"] == V.CUMPLE


def test_cambio_garaje_a_local():
    exp, tr = _tr("adicion_modificacion_cambio_uso", "cambio_de_uso", frente_local=2.5, area_local=12)
    res = {r["item"]: r["estado"] for r in V.verificar(exp, tr)}
    assert res["Frente del local (garaje a local)"] == V.NO_CUMPLE
    assert res["Área del local (garaje a local)"] == V.CUMPLE


def test_subir_desde_lista_y_paquete_completo():
    exp, tr = _tr("nomenclatura_dian", "certificado")
    C.generar(tr["id"])
    docs = [i for i in C.items(tr["id"]) if i["seccion"] == "documentos"]
    assert len(docs) == 2
    with pytest.raises(ValueError):
        C.marcar_paquete(tr["id"], True, "f")
    cat = next(i for i in docs if "certificado_catastro" in i["item_id"])
    r = C.subir_documento_item(cat["id"], _arch("catastro.pdf"), "f", (HOY - timedelta(days=40)).isoformat())
    assert r["estado"] == "no_cumple"                                   # más de un mes
    r = C.subir_documento_item(cat["id"], _arch("catastro2.pdf"), "f", (HOY - timedelta(days=5)).isoformat())
    assert r["estado"] == "cumple"
    sol = next(i for i in docs if "solicitud_tramite" in i["item_id"])
    C.subir_documento_item(sol["id"], _arch("solicitud.pdf"), "f")
    pq = C.marcar_paquete(tr["id"], True, "f", HOY.isoformat())
    assert pq["completo"] and pq["fecha_completo"] == HOY.isoformat()
    assert E.tramite(tr["id"])["estado"] == "en_revision"
    assert not C.marcar_paquete(tr["id"], False, "f", observacion="reabre")["completo"]


def test_forzar_paquete_exige_observacion():
    exp, tr = _tr("nomenclatura_dian", "certificado")
    with pytest.raises(ValueError):
        C.marcar_paquete(tr["id"], True, "f", forzar=True)
    assert C.marcar_paquete(tr["id"], True, "f", forzar=True, observacion="Se recibe con compromiso")["completo"]


def test_items_de_documentos_se_actualizan_al_cambiar_pisos():
    exp, tr = _tr("construccion_urbana", "obra_nueva", n_pisos=4)
    C.generar(tr["id"])
    assert any(i["item_id"] == "doc:estudio_suelos" for i in C.items(tr["id"]))
    E.editar_tramite(tr["id"], {"datos": {**tr["datos"], "n_pisos": 2}}, "f")
    C.generar(tr["id"])
    ids = {i["item_id"] for i in C.items(tr["id"])}
    assert "doc:apique" in ids and "doc:estudio_suelos" not in ids
