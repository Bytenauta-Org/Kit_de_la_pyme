"""Veredicto y nota: las 17 combinaciones del oro (incluidas las dos cifras publicadas en la W37)."""

from __future__ import annotations

import pytest

from kit_pyme.puntuacion import UMBRALES, nota_por_reglas, veredicto_por_reglas
from tests.conftest import leer_oro

RESUMEN = leer_oro("resumen.json")


def test_umbrales_del_contrato():
    assert UMBRALES == RESUMEN["UMBRALES"]


@pytest.mark.parametrize("v", RESUMEN["veredictos"], ids=lambda v: v["nombre"])
def test_veredicto_y_nota(v):
    veredicto = veredicto_por_reglas(v["aciertos"], v["casos"], v["coste_eur"], v.get("sinRespuesta", 0))
    assert veredicto == v["veredicto"]
    nota = nota_por_reglas(
        veredicto,
        v["aciertos"],
        v["casos"],
        v["coste_eur"],
        v["fallos"],
        v.get("sinRespuesta", 0),
        v.get("erroresServicio", 0),
    )
    assert nota == v["nota"]


@pytest.mark.parametrize(
    ("aciertos", "casos", "coste", "sin_respuesta", "esperado"),
    [
        (19, 20, 0.5, 0, "lo-usaria-el-lunes"),
        (20, 20, 2, 0, "todavia-no"),
        (14, 20, 0.1, 0, "todavia-no"),
        (11, 20, 0.1, 0, "humo"),
        (0, 0, 0, 0, "todavia-no"),
        (0, 25, 0, 25, "todavia-no"),
        (0, 25, 0, 20, "todavia-no"),
        (0, 25, 0, 5, "humo"),
    ],
)
def test_umbrales_como_en_probar_test_ts(aciertos, casos, coste, sin_respuesta, esperado):
    assert veredicto_por_reglas(aciertos, casos, coste, sin_respuesta) == esperado
