"""La puntuación es la del blog: 100 % con la verdad, y los mismos textos de fallo regla por regla."""

from __future__ import annotations

import pytest

from kit_pyme.puntuacion import AUSENTE, puntuar, puntuar_caso
from kit_pyme.tareas import ORDEN_TAREAS, Caso
from tests.conftest import leer_oro, respuesta_o_ausente, respuestas_verdad

RESUMEN = leer_oro("resumen.json")
NEGATIVOS = leer_oro("fallos-negativos.json")


def caso_de(tareas, id_tarea: str, id_caso: str) -> Caso:
    return next(c for c in tareas[id_tarea].preparar() if c.id == id_caso)


@pytest.mark.parametrize("id_tarea", ORDEN_TAREAS)
def test_cada_tarea_puntua_cien_por_cien_con_sus_respuestas_verdaderas(id_tarea, tareas):
    casos = tareas[id_tarea].preparar()
    filas = respuestas_verdad(id_tarea)
    assert [f["id"] for f in filas] == [c.id for c in casos]
    p = puntuar(id_tarea, casos, [f["respuesta"] for f in filas])
    assert p.todos_los_fallos == []
    assert p.aciertos == len(casos) == RESUMEN["verdad_100"][id_tarea]["casos"]


@pytest.mark.parametrize("neg", NEGATIVOS, ids=[f"{n['tarea']}/{n['caso']}/{n['nombre']}" for n in NEGATIVOS])
def test_fallos_negativos_regla_por_regla(neg, tareas):
    """112 respuestas trucadas: el ``ok`` y el texto de fallo tienen que ser los del TypeScript."""
    r = puntuar_caso(neg["tarea"], caso_de(tareas, neg["tarea"], neg["caso"]), respuesta_o_ausente(neg))
    assert r.ok == neg["ok"]
    assert r.fallo == neg.get("fallo")


def test_puntuar_recorta_a_tres_fallos_y_cuenta_bien(tareas):
    e = RESUMEN["puntuar_ejemplo"]
    casos = [caso_de(tareas, e["tarea"], i) for i in e["casos"]]
    p = puntuar(e["tarea"], casos, e["respuestas"])
    assert p.aciertos == e["resultado"]["aciertos"]
    assert p.fallos == e["resultado"]["fallos"]
    assert p.todos_los_fallos == e["resultado"]["todos_los_fallos"]


def test_sin_respuesta_frente_a_null(tareas):
    e = RESUMEN["puntuar_sin_respuesta"]
    casos = tareas["extraer-pedidos"].preparar()[:2]
    p = puntuar("extraer-pedidos", casos, [AUSENTE, None])
    assert p.aciertos == e["aciertos"]
    assert p.todos_los_fallos == e["todos_los_fallos"]


def test_respuestas_que_faltan_cuentan_como_ausentes(tareas):
    casos = tareas["resumir-correos"].preparar()[:3]
    p = puntuar("resumir-correos", casos, [])
    assert p.aciertos == 0
    assert p.todos_los_fallos == [f"Correo 0{i}: el modelo no devolvió una respuesta válida" for i in (1, 2, 3)]


# ----- una regla, un test legible (los oros ya cubren cada regla; esto es para quien lea el código) -----


def _verdad(id_tarea: str, id_caso: str) -> dict:
    return next(f["respuesta"] for f in respuestas_verdad(id_tarea) if f["id"] == id_caso)


def test_regla_pedido_precio_que_no_es_de_tarifa(tareas):
    r = _verdad("extraer-pedidos", "pedido-01")
    r["lineas"][0]["precio_caja"] = 26.40  # tarifa general; Serrano paga 24,29
    res = puntuar_caso("extraer-pedidos", caso_de(tareas, "extraer-pedidos", "pedido-01"), r)
    assert res.fallo == "Pedido 01: en CONS-ATUN-OL-120 puso 26,40 € donde la tarifa dice 24,29 €"


def test_regla_pedido_cantidad_mal_leida(tareas):
    r = _verdad("extraer-pedidos", "pedido-01")
    r["lineas"][0]["cantidad_cajas"] = "400"
    res = puntuar_caso("extraer-pedidos", caso_de(tareas, "extraer-pedidos", "pedido-01"), r)
    assert res.fallo == "Pedido 01: en CONS-ATUN-OL-120 leyó 400 cajas donde ponía 40"


def test_regla_pedido_referencia_inexistente_sin_avisar(tareas):
    r = _verdad("extraer-pedidos", "pedido-07")
    r["incidencias"] = []
    res = puntuar_caso("extraer-pedidos", caso_de(tareas, "extraer-pedidos", "pedido-07"), r)
    assert res.fallo == "Pedido 07: no avisó de que la referencia CONS-ATUN-OL-200 no existe en la tarifa"


def test_regla_correo_categoria_mal(tareas):
    res = puntuar_caso(
        "resumir-correos",
        caso_de(tareas, "resumir-correos", "correo-05"),
        {"categoria": "consulta", "urgencia": "baja"},
    )
    assert res.fallo is not None
    assert res.fallo.startswith("Correo 05: lo clasificó como «consulta» cuando era spam (")


def test_regla_contrato_dato_bien_sin_clausula(tareas):
    r = _verdad("buscar-en-contrato", "p01")
    r["clausula"] = ""
    res = puntuar_caso("buscar-en-contrato", caso_de(tareas, "buscar-en-contrato", "p01"), r)
    assert res.fallo == (
        "Contrato p01: acertó el dato pero no citó la cláusula 9.2, así que no hay forma de comprobarlo sin releer"
    )


def test_regla_factura_vencimiento_mal(tareas):
    r = _verdad("clasificar-facturas", "factura-08")
    r["vencimiento"] = "2026-10-05"
    res = puntuar_caso("clasificar-facturas", caso_de(tareas, "clasificar-facturas", "factura-08"), r)
    assert res.fallo == "Factura 08: vencimiento 2026-10-05 donde tocaba 05/09/2026"


def test_regla_factura_duplicada_no_detectada(tareas):
    r = _verdad("clasificar-facturas", "factura-09")
    r["duplicada"] = False
    res = puntuar_caso("clasificar-facturas", caso_de(tareas, "clasificar-facturas", "factura-09"), r)
    assert res.fallo == (
        "Factura 09: no vio que la MIS/26/0771 de Mantenimientos Industriales Segura S.L. ya estaba contabilizada (duplicada)"
    )


def test_regla_recordatorio_amenaza_cuando_no_toca(tareas):
    r = _verdad("redactar-recordatorio", "recordatorio-02")
    r["cuerpo"] += "\nSi no, iniciaremos acciones legales."
    res = puntuar_caso("redactar-recordatorio", caso_de(tareas, "redactar-recordatorio", "recordatorio-02"), r)
    assert res.fallo == (
        "Recordatorio 02: usa «acciones legales» en un recordatorio de tono amable a Sabores de Levante Online S.L."
    )


def test_regla_recordatorio_formal_sin_plazo_ni_advertencia(tareas):
    r = _verdad("redactar-recordatorio", "recordatorio-01")  # un amable, sin plazo ni advertencia
    caso = caso_de(tareas, "redactar-recordatorio", "recordatorio-10")
    r["cuerpo"] = (
        r["cuerpo"].replace("26/1135", "26/1124").replace("4312,60", "421,90").replace("07/09/2026", "30/06/2026")
    )
    res = puntuar_caso("redactar-recordatorio", caso, r)
    assert res.fallo == (
        "Recordatorio 10: un último aviso tiene que fijar plazo y advertir de suspensión o intereses, y no lo hace"
    )


def test_regla_recordatorio_demasiado_largo(tareas):
    r = _verdad("redactar-recordatorio", "recordatorio-01")
    r["cuerpo"] += " bla" * 230
    res = puntuar_caso("redactar-recordatorio", caso_de(tareas, "redactar-recordatorio", "recordatorio-01"), r)
    assert res.fallo is not None
    assert res.fallo.endswith("palabras para reclamar una factura; nadie lo lee entero")
