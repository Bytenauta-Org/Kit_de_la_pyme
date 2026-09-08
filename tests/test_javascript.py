"""La emulación de JavaScript da lo mismo que JavaScript (tablas de ``resumen.json``)."""

from __future__ import annotations

import pytest

from kit_pyme import javascript as js
from tests.conftest import leer_oro

REDONDEOS = leer_oro("resumen.json")["redondeos"]


@pytest.mark.parametrize("caso", REDONDEOS["Math.round(x*10000)/10000"], ids=lambda c: str(c["x"]))
def test_coste_a_cuatro_decimales(caso):
    assert js.redondear(caso["x"] * 10000) / 10000 == caso["salida"]


@pytest.mark.parametrize("caso", REDONDEOS["Math.round(ms/100)/10 (segundos)"], ids=lambda c: str(c["ms"]))
def test_segundos_a_una_decima(caso):
    assert js.redondear(caso["ms"] / 100) / 10 == caso["salida"]


@pytest.mark.parametrize("caso", REDONDEOS["toFixed(1) sobre céntimos"], ids=lambda c: str(c["x"]))
def test_to_fixed_1(caso):
    assert js.a_fijo(caso["x"], 1) == caso["salida"]


@pytest.mark.parametrize("caso", REDONDEOS["toFixed(2)"], ids=lambda c: str(c["x"]))
def test_to_fixed_2(caso):
    assert js.a_fijo(caso["x"], 2) == caso["salida"]


@pytest.mark.parametrize(
    ("x", "esperado"),
    [
        (2.5, 3),
        (-2.5, -2),
        (0.49999999999999994, 0),
        (3821.5, 3822),
        (-0.5, 0),
        (1.4999, 1),
    ],
)
def test_math_round(x, esperado):
    assert js.redondear(x) == esperado


@pytest.mark.parametrize(
    ("n", "esperado"),
    [
        (1.0, "1"),
        (1, "1"),
        (24.5, "24.5"),
        (1e21, "1e+21"),
        (1e-7, "1e-7"),
        (0.00001, "0.00001"),
        (0.000001, "0.000001"),
        (1e16, "10000000000000000"),
        (123.456, "123.456"),
        (-0.0, "0"),
        (-1234.5, "-1234.5"),
        (2.5e-8, "2.5e-8"),
        (1.5e22, "1.5e+22"),
        (0.1 + 0.2, "0.30000000000000004"),
    ],
)
def test_string_de_numero(n, esperado):
    assert js.texto_de_numero(n) == esperado


@pytest.mark.parametrize(
    ("s", "esperado"),
    [
        ("1e3", 1000.0),
        ("0x10", 16.0),
        ("0b101", 5.0),
        ("0o17", 15.0),
        (".5", 0.5),
        ("+5", 5.0),
        ("1.", 1.0),
        ("12abc", None),
        ("1_000", None),
        ("Infinity", None),
        ("NaN", None),
        ("-0x10", None),
        ("1e", None),
    ],
)
def test_number_de_cadena(s, esperado):
    assert js.numero_de_texto(s) == esperado


def test_trim_y_espacios_de_javascript():
    assert js.recortar("﻿ x  ") == "x"
    assert js.colapsar_espacios("a  b\tc") == "a b c"
    # U+001C es espacio para Python pero no para JavaScript: se queda.
    assert js.colapsar_espacios("ab") == "ab"


def test_json_stringify_compacto():
    assert js.json_texto({"a": 1.0, "b": "é", "c": [True, None, 2.5]}) == '{"a":1,"b":"é","c":[true,null,2.5]}'
    assert js.json_texto([1, "x"]) == '[1,"x"]'
