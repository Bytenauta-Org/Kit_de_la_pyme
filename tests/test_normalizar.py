"""Cada utilidad de normalización devuelve lo mismo que la del blog (tablas de ``resumen.json``)."""

from __future__ import annotations

import pytest

from kit_pyme import normalizar as n
from tests.conftest import leer_oro, sin_undefined

UTILIDADES = leer_oro("resumen.json")["utilidades"]


def _id(caso):
    return repr(caso.get("entrada"))[:40]


@pytest.mark.parametrize("caso", UTILIDADES["leerNumero"], ids=_id)
def test_leer_numero(caso):
    assert n.leer_numero(sin_undefined(caso["entrada"])) == sin_undefined(caso["salida"])


@pytest.mark.parametrize("caso", UTILIDADES["leerFecha"], ids=_id)
def test_leer_fecha(caso):
    assert n.leer_fecha(sin_undefined(caso["entrada"])) == sin_undefined(caso["salida"])


@pytest.mark.parametrize("caso", UTILIDADES["normalizarTexto"], ids=_id)
def test_normalizar_texto(caso):
    assert n.normalizar_texto(sin_undefined(caso["entrada"])) == caso["salida"]


@pytest.mark.parametrize("caso", UTILIDADES["normalizarReferencia"], ids=_id)
def test_normalizar_referencia(caso):
    assert n.normalizar_referencia(sin_undefined(caso["entrada"])) == caso["salida"]


@pytest.mark.parametrize("caso", UTILIDADES["formatearEuros"], ids=_id)
def test_formatear_euros(caso):
    assert n.formatear_euros(caso["entrada"]) == caso["salida"]


@pytest.mark.parametrize(
    ("v", "esperado"),
    [
        (True, True),
        (False, False),
        ("Sí", True),
        ("si", True),
        ("duplicada", True),
        ("YES", True),
        (1, True),
        ("no", False),
        ("0", False),
        ("", False),
        (None, False),
        ("quizás", None),
        (2, None),
    ],
)
def test_leer_booleano(v, esperado):
    assert n.leer_booleano(v) == esperado


@pytest.mark.parametrize(
    ("id_caso", "esperado"),
    [
        ("pedido-06", "Pedido 06"),
        ("correo-30", "Correo 30"),
        ("factura-08", "Factura 08"),
        ("recordatorio-01", "Recordatorio 01"),
        ("PEDIDO-1", "PEDIDO 1"),
        ("otro-7", "otro 7"),
        ("p01", "p01"),
    ],
)
def test_etiqueta(id_caso, esperado):
    assert n.etiqueta(id_caso) == esperado


def test_objeto_y_lista():
    assert n.objeto({"a": 1}) == {"a": 1}
    assert n.objeto([1]) == {}
    assert n.objeto(None) == {}
    assert n.lista([1]) == [1]
    assert n.lista("x") == []
