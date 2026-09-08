"""Coste, nombre del modelo y el 400 de la temperatura: igual que ``conector.ts``."""

from __future__ import annotations

import pytest

from kit_pyme import cliente
from tests.conftest import leer_oro

UTILIDADES = leer_oro("resumen.json")["utilidades"]
PRECIOS = cliente.cargar_precios()


def test_la_tabla_de_precios_es_la_del_blog():
    assert PRECIOS == {
        "anthropic/claude-haiku-4-5": {"entrada": 0.9, "salida": 4.5},
        "anthropic/claude-sonnet-5": {"entrada": 2.8, "salida": 14},
        "anthropic/claude-opus-5": {"entrada": 14, "salida": 70},
        "por_defecto": {"entrada": 3, "salida": 15},
    }


@pytest.mark.parametrize("c", UTILIDADES["estimarCoste"], ids=lambda c: f"{c['modelo']}/{c['tokens_entrada']}")
def test_estimar_coste(c):
    assert cliente.estimar_coste(c["modelo"], c["tokens_entrada"], c["tokens_salida"], PRECIOS) == c["coste_eur"]


@pytest.mark.parametrize("c", UTILIDADES["normalizarModelo"], ids=lambda c: c["modelo"])
def test_normalizar_modelo(c):
    assert cliente.normalizar_modelo(c["modelo"], c["principal"]) == c["salida"]


@pytest.mark.parametrize("c", UTILIDADES["esTemperaturaObsoleta"], ids=lambda c: c["cuerpo"][:25])
def test_es_temperatura_obsoleta(c):
    assert cliente.es_temperatura_obsoleta(c["estado"], c["cuerpo"]) is c["salida"]


@pytest.mark.parametrize(
    ("modelo", "esperado"),
    [
        ("anthropic/claude-opus-5", ("anthropic", "claude-opus-5")),
        ("claude-haiku-4-5", ("anthropic", "claude-haiku-4-5")),
        ("google-ai-studio/gemini-4-pro", ("google", "gemini-4-pro")),
        ("openai/gpt-6", ("openai", "gpt-6")),
        ("mi-proveedor/a/b", ("mi-proveedor", "a/b")),
    ],
)
def test_partir_modelo(modelo, esperado):
    assert cliente.partir_modelo(modelo) == esperado


def test_endpoint_directo():
    assert cliente.endpoint_directo("anthropic/claude-haiku-4-5") == "https://api.anthropic.com/v1/chat/completions"
    assert cliente.endpoint_directo("openai/gpt-6") == "https://api.openai.com/v1/chat/completions"
    assert cliente.endpoint_directo("ollama/llama") is None


def test_uso_se_suma_campo_a_campo():
    u = cliente.Uso(1, 2, 0.5) + cliente.Uso(10, 20, 0.25)
    assert u.como_dict() == {"tokens_entrada": 11, "tokens_salida": 22, "coste_eur": 0.75}


def test_error_cliente_clasifica():
    assert cliente.ErrorCliente("x", 503).es_del_servicio
    assert cliente.ErrorCliente("x", 429).es_del_servicio
    assert cliente.ErrorCliente("x", red=True).es_del_servicio
    assert not cliente.ErrorCliente("JSON inválido").es_del_servicio
    assert cliente.ErrorCliente("x", 404).no_disponible
    assert not cliente.ErrorCliente("x", 429).no_disponible
    assert not cliente.ErrorCliente("x", 500).no_disponible
