"""Extracción de JSON, rescate de claves y validación: igual que ``conector.ts`` e ``index.ts``."""

from __future__ import annotations

import pytest

from kit_pyme import esquema
from tests.conftest import leer_oro

RESUMEN = leer_oro("resumen.json")
UTILIDADES = RESUMEN["utilidades"]


@pytest.mark.parametrize("caso", UTILIDADES["normalizarClaves"], ids=lambda c: str(list(c["datos"]))[:40])
def test_normalizar_claves(caso):
    assert esquema.normalizar_claves(caso["datos"], caso["esquema"]) == caso["salida"]


def test_normalizar_claves_no_toca_el_original():
    datos = {"base_imponible": 1}
    esquema.normalizar_claves(datos, {"required": ["base"]})
    assert datos == {"base_imponible": 1}


@pytest.mark.parametrize("caso", UTILIDADES["extraerJson"], ids=lambda c: repr(c["entrada"])[:30])
def test_extraer_json(caso):
    if "error" in caso:
        with pytest.raises(esquema.ErrorJson) as e:
            esquema.extraer_json(caso["entrada"])
        assert str(e.value) == caso["error"]
    else:
        assert esquema.extraer_json(caso["entrada"]) == caso["salida"]


def test_extraer_json_repara_un_json_cortado():
    cortado = '{"cliente": "X", "lineas": [{"referencia": "A", "cantidad_cajas": 1}, {"referencia": "B", "cant'
    assert esquema.extraer_json(cortado) == {
        "cliente": "X",
        "lineas": [{"referencia": "A", "cantidad_cajas": 1}],
    }


def test_extraer_json_rechaza_nan_como_javascript():
    with pytest.raises(esquema.ErrorJson):
        esquema.extraer_json("NaN")


@pytest.mark.parametrize("caso", UTILIDADES["validarContraEsquema"], ids=lambda c: repr(c["datos"])[:30])
def test_validar_contra_esquema(caso):
    assert esquema.validar_contra_esquema(caso["datos"], caso["esquema"]) == caso["salida"]


@pytest.mark.parametrize("id_tarea", list(RESUMEN["tareas"]))
def test_linea_formato(id_tarea, tareas):
    t = tareas[id_tarea]
    assert esquema.con_claves_explicitas(t.prompt, t.esquema) == t.prompt + RESUMEN["tareas"][id_tarea]["linea_formato"]


def test_sin_required_no_hay_linea_formato():
    assert esquema.con_claves_explicitas("Haz esto.", {"type": "object"}) == "Haz esto."
    assert esquema.con_claves_explicitas("Haz esto.", None) == "Haz esto."


def test_escapar_crudos():
    assert esquema.escapar_crudos('{"a":"x\ny\t\x01"}') == '{"a":"x\\ny\\t\\u0001"}'
    assert esquema.escapar_crudos('{"a":"ya \\n escapado"}') == '{"a":"ya \\n escapado"}'
