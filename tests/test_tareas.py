"""Los prompts y las entradas que compone el kit son byte a byte los del blog."""

from __future__ import annotations

import hashlib
import json

import pytest

from kit_pyme.tareas import (
    ORDEN_TAREAS,
    ErrorTarea,
    cargar_tarea,
    ids_tareas,
    leer_texto,
    raiz_del_kit,
)
from tests.conftest import RAIZ, leer_oro

RESUMEN = leer_oro("resumen.json")
CASOS = [(t, c["id"]) for t, v in RESUMEN["tareas"].items() for c in v["casos"]]


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("id_tarea", ORDEN_TAREAS)
def test_prompt_identico_al_del_blog(id_tarea, tareas):
    o = RESUMEN["tareas"][id_tarea]
    t = tareas[id_tarea]
    assert len(t.prompt.encode("utf-8")) == o["prompt_bytes"]
    assert sha(t.prompt) == o["prompt_sha256"]
    assert "\r" not in t.prompt


@pytest.mark.parametrize("id_tarea", ORDEN_TAREAS)
def test_mensaje_de_sistema_identico_al_enviado(id_tarea, tareas):
    o = RESUMEN["tareas"][id_tarea]
    assert sha(tareas[id_tarea].system) == o["system_enviado_sha256"]


@pytest.mark.parametrize("id_tarea", ORDEN_TAREAS)
def test_nombre_descripcion_max_tokens_y_esquema(id_tarea, tareas):
    o = RESUMEN["tareas"][id_tarea]
    t = tareas[id_tarea]
    assert t.nombre == o["nombre"]
    assert t.descripcion == o["descripcion"]
    assert t.max_tokens == o["max_tokens"]
    assert t.esquema["required"] == o["required"]


@pytest.mark.parametrize(("id_tarea", "id_caso"), CASOS, ids=[f"{t}/{c}" for t, c in CASOS])
def test_entrada_de_cada_caso(id_tarea, id_caso, tareas):
    esperado = next(c for c in RESUMEN["tareas"][id_tarea]["casos"] if c["id"] == id_caso)
    caso = next(c for c in tareas[id_tarea].preparar() if c.id == id_caso)
    assert len(caso.entrada.encode("utf-8")) == esperado["entrada_bytes"]
    assert sha(caso.entrada) == esperado["entrada_sha256"]


@pytest.mark.parametrize("id_tarea", ORDEN_TAREAS)
def test_los_casos_van_en_el_orden_del_fichero_de_verdad(id_tarea, tareas):
    assert [c.id for c in tareas[id_tarea].preparar()] == [c["id"] for c in RESUMEN["tareas"][id_tarea]["casos"]]


def test_prompt_del_recordatorio_sale_de_cobros_verdad(tareas):
    """``tareas.ts`` interpola firma, tonos y fecha; el JSON lleva el texto resuelto y tiene que coincidir."""
    vb = tareas["redactar-recordatorio"].verdad
    hoy = "/".join(reversed(vb["fecha_referencia"].split("-")))
    esperado = (
        f"Eres {vb['firma']['nombre']}, de {vb['firma']['cargo']} de Conservas Marjal Blanca S.L. "
        "(Almoradí, Alicante). Escribes correos de recordatorio de cobro a clientes con los que "
        "queremos seguir trabajando.\n\nReglas de la casa:\n"
        "- Un correo corto (menos de 200 palabras), en español, dirigido a la persona de contacto por "
        "su nombre de pila, con asunto.\n"
        "- Tiene que decir siempre el número de factura, el importe pendiente en euros y la fecha de "
        "vencimiento. Si hubo un pago parcial, reconócelo y reclama solo el resto.\n"
        "- Tono según lo que te indiquen:\n"
        f"  · amable: {vb['tonos']['amable']['descripcion']}.\n"
        f"  · firme: {vb['tonos']['firme']['descripcion']}.\n"
        f"  · formal: {vb['tonos']['formal']['descripcion']}.\n"
        f"- Ofrece siempre la cuenta para el pago (IBAN {vb['firma']['iban']}) y un teléfono "
        f"({vb['firma']['telefono']}) por si el pago ya está hecho o hay algún problema con la factura.\n"
        "- Nunca amenaces con abogados ni denuncias; nunca insultes; nunca digas que «el sistema» lo ha "
        "enviado.\n"
        f"- Firma como {vb['firma']['nombre']}, {vb['firma']['cargo']}, Conservas Marjal Blanca S.L.\n\n"
        f"Hoy es {hoy}. Responde solo con el JSON del esquema."
    )
    assert tareas["redactar-recordatorio"].prompt == esperado


@pytest.mark.parametrize(
    ("id_tarea", "marcador"),
    [
        ("extraer-pedidos", "{{datos/pedidos/tarifa.csv}}"),
        ("extraer-pedidos", "{{datos/pedidos/clientes.csv}}"),
        ("buscar-en-contrato", "{{datos/contrato/contrato.txt}}"),
        ("clasificar-facturas", "{{datos/facturas/registro-previo.csv}}"),
    ],
)
def test_tarea_json_lleva_marcadores_y_no_copias_de_los_datos(id_tarea, marcador):
    d = json.loads((RAIZ / "tareas" / id_tarea / "tarea.json").read_text(encoding="utf-8"))
    assert marcador in d["prompt"]
    assert d["sha256"]["prompt"] == RESUMEN["tareas"][id_tarea]["prompt_sha256"]


def test_orden_canonico_de_las_tareas(raiz):
    assert ids_tareas(raiz) == list(ORDEN_TAREAS)


def test_leer_texto_no_traduce_saltos(raiz):
    assert leer_texto(raiz / "datos" / "cobros" / "cobros.csv").count("\r") == 0


def test_raiz_del_kit_por_variable_de_entorno(monkeypatch, raiz, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KIT_PYME_RAIZ", str(raiz))
    assert raiz_del_kit() == raiz.resolve()
    monkeypatch.delenv("KIT_PYME_RAIZ")
    # Sin variable ni carpeta a la vista, cae en la carpeta del paquete (el clon).
    assert raiz_del_kit() == raiz.resolve()
    with pytest.raises(ErrorTarea):
        raiz_del_kit(tmp_path)


def test_tarea_desconocida(raiz):
    with pytest.raises(ErrorTarea):
        cargar_tarea("no-existe", raiz)
