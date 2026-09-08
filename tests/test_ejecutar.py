"""``ejecutar`` contra un servidor falso local (``http.server``) que devuelve respuestas grabadas.

Es el equivalente de ``test/pruebas/probar.test.ts`` del blog: con 1200/150 tokens por caso y
Haiku, quince casos cuestan 0,0263 €; un 4xx aborta sin reintentar; un ``{}`` con HTTP 200
tres veces seguidas deja el caso sin respuesta y la tarea sigue; el 400 de ``temperature``
se aprende y no vuelve a viajar.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from kit_pyme.cliente import Cliente, Peticion, cargar_precios
from kit_pyme.ejecutar import ModeloNoDisponible, ejecutar_tarea
from tests.conftest import respuestas_verdad
from tests.test_cli import CLAVES_RESULTADO

Contestador = Callable[[dict[str, Any], int], tuple[int, Any]]


class ServidorFalso:
    """Un endpoint compatible con OpenAI en 127.0.0.1 que contesta lo que le diga el test."""

    def __init__(self) -> None:
        self.peticiones: list[dict[str, Any]] = []
        self.contestar: Contestador = lambda cuerpo, n: (200, {})
        self._candado = threading.Lock()
        servidor = self

        class Manejador(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                largo = int(self.headers.get("content-length") or 0)
                cuerpo = json.loads(self.rfile.read(largo).decode("utf-8"))
                with servidor._candado:
                    servidor.peticiones.append(
                        {
                            "ruta": self.path,
                            "cabeceras": {k.lower(): v for k, v in self.headers.items()},
                            "cuerpo": cuerpo,
                        }
                    )
                    n = len(servidor.peticiones)
                estado, respuesta = servidor.contestar(cuerpo, n)
                datos = (respuesta if isinstance(respuesta, str) else json.dumps(respuesta)).encode("utf-8")
                self.send_response(estado)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(datos)))
                self.end_headers()
                self.wfile.write(datos)

            def log_message(self, *args: Any) -> None:
                pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
        self.url = f"http://127.0.0.1:{self.http.server_address[1]}/v1/chat/completions"
        self.hilo = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.hilo.start()

    def parar(self) -> None:
        self.http.shutdown()
        self.http.server_close()

    def de_modelo(
        self,
        contenido: Any,
        tokens: tuple[int, int] = (1200, 150),
        modelo: str = "claude-haiku-4-5",
    ) -> dict:
        return {
            "model": modelo,
            "choices": [
                {
                    "message": {
                        "content": contenido
                        if isinstance(contenido, str)
                        else json.dumps(contenido, ensure_ascii=False)
                    }
                }
            ],
            "usage": {"prompt_tokens": tokens[0], "completion_tokens": tokens[1]},
        }


@pytest.fixture
def servidor():
    s = ServidorFalso()
    yield s
    s.parar()


@pytest.fixture
def cliente(servidor):
    return Cliente(
        endpoint=servidor.url,
        clave="clave-de-prueba",
        precios=cargar_precios(),
        dormir=lambda s: None,
    )


def correcta_por_entrada(tarea) -> dict[str, Any]:
    """Entrada de cada caso → respuesta correcta grabada."""
    verdad = {f["id"]: f["respuesta"] for f in respuestas_verdad(tarea.id)}
    return {c.entrada: verdad[c.id] for c in tarea.preparar()}


def test_todo_bien_quince_casos_de_contrato(servidor, cliente, tareas):
    tarea = tareas["buscar-en-contrato"]
    correctas = correcta_por_entrada(tarea)
    servidor.contestar = lambda cuerpo, n: (
        200,
        servidor.de_modelo(correctas[cuerpo["messages"][1]["content"]]),
    )
    informe = ejecutar_tarea(cliente, tarea, "anthropic/claude-haiku-4-5")
    r = informe.resultado
    assert list(r) == CLAVES_RESULTADO
    assert (r["casos"], r["aciertos"], r["fallos"]) == (15, 15, [])
    assert r["coste_eur"] == 0.0263  # Math.round(15·(1200·0.9+150·4.5)/1e6·10000)/10000
    assert r["veredicto"] == "lo-usaria-el-lunes"
    assert r["nota"].startswith("Acertó los 15 casos a 0,2 céntimos por caso")
    assert r["segundos"] >= 0
    assert r["tarea_nombre"] == tarea.nombre
    assert informe.uso.tokens_entrada == 15 * 1200
    assert len(servidor.peticiones) == 15
    p = servidor.peticiones[0]
    assert p["cabeceras"]["authorization"] == "Bearer clave-de-prueba"
    assert p["cabeceras"]["content-type"] == "application/json"
    assert p["cuerpo"]["model"] == "claude-haiku-4-5"
    assert p["cuerpo"]["temperature"] == 0
    assert p["cuerpo"]["max_tokens"] == tarea.max_tokens
    assert p["cuerpo"]["messages"][0] == {"role": "system", "content": tarea.system}
    assert {q["cuerpo"]["messages"][1]["content"] for q in servidor.peticiones} == set(correctas)
    detalle = informe.detalle("anthropic/claude-haiku-4-5")
    assert detalle["realizada"] is True
    assert detalle["uso"]["tokens_salida"] == 15 * 150
    assert all(c["ok"] and "uso" in c and c["texto_modelo"] for c in detalle["casos"])


def test_un_4xx_aborta_sin_reintentar(servidor, cliente, tareas):
    servidor.contestar = lambda cuerpo, n: (404, {"error": {"message": "model not found"}})
    with pytest.raises(ModeloNoDisponible) as e:
        ejecutar_tarea(cliente, tareas["resumir-correos"], "openai/gpt-6", concurrencia=1)
    assert "respondió 404 para openai/gpt-6: no disponible por API todavía" in str(e.value)
    assert len(servidor.peticiones) == 1


def test_respuesta_vacia_tres_veces_deja_el_caso_sin_respuesta_y_sigue(servidor, cliente, tareas):
    tarea = tareas["buscar-en-contrato"]
    correctas = correcta_por_entrada(tarea)
    casos = tarea.preparar()
    roto = casos[2].entrada

    def contestar(cuerpo, n):
        entrada = cuerpo["messages"][1]["content"]
        if entrada == roto:
            return 200, {}
        return 200, servidor.de_modelo(correctas[entrada])

    servidor.contestar = contestar
    r = ejecutar_tarea(cliente, tarea, "anthropic/claude-haiku-4-5", concurrencia=1).resultado
    assert (r["casos"], r["aciertos"]) == (15, 14)
    assert r["sin_respuesta"] == 1
    assert "errores_servicio" not in r
    # El blog etiqueta «Pedido 03» y «Correo 07», pero deja «p03» tal cual: la etiqueta solo
    # traduce pedido/correo/factura/recordatorio (src/pruebas/puntuar.ts:79-84).
    assert r["fallos"] == ["p03: el modelo no devolvió una respuesta válida"]
    assert r["veredicto"] == "lo-usaria-el-lunes"
    assert sum(1 for p in servidor.peticiones if p["cuerpo"]["messages"][1]["content"] == roto) == 3
    assert len(servidor.peticiones) == 17


def test_el_400_de_temperature_se_aprende_y_no_vuelve_a_viajar(servidor, cliente, tareas):
    tarea = tareas["redactar-recordatorio"]
    correctas = correcta_por_entrada(tarea)

    def contestar(cuerpo, n):
        if "temperature" in cuerpo:
            return 400, {"error": {"message": "`temperature` is not supported in this model"}}
        return 200, servidor.de_modelo(correctas[cuerpo["messages"][1]["content"]], modelo="claude-opus-5")

    servidor.contestar = contestar
    r = ejecutar_tarea(cliente, tarea, "anthropic/claude-opus-5", concurrencia=1).resultado
    assert (r["aciertos"], r["casos"]) == (10, 10)
    assert "sin_respuesta" not in r
    con_temperatura = [p for p in servidor.peticiones if "temperature" in p["cuerpo"]]
    assert len(con_temperatura) == 1
    assert len(servidor.peticiones) == 11
    assert "anthropic/claude-opus-5" in cliente.sin_temperatura
    assert r["coste_eur"] == 0.273  # 10 · (1200·14 + 150·70) / 1e6


def test_coste_con_opus_5(servidor, cliente, tareas):
    tarea = tareas["redactar-recordatorio"]
    correctas = correcta_por_entrada(tarea)
    servidor.contestar = lambda cuerpo, n: (
        200,
        servidor.de_modelo(correctas[cuerpo["messages"][1]["content"]], modelo="claude-opus-5"),
    )
    r = ejecutar_tarea(cliente, tarea, "anthropic/claude-opus-5").resultado
    # 10 casos · (1200·14 + 150·70) / 1e6 = 0.273 €, o sea 2,7 céntimos por caso: por debajo del
    # umbral de 5 céntimos, así que el precio de Opus no baja el veredicto en una tarea corta.
    assert r["coste_eur"] == 0.273
    assert r["veredicto"] == "lo-usaria-el-lunes"
    assert "2,7 céntimos por caso" in r["nota"]


def test_un_429_se_reintenta_y_los_intentos_perdidos_se_cobran(servidor, cliente, tareas):
    tarea = tareas["resumir-correos"]
    correctas = correcta_por_entrada(tarea)
    casos = tarea.preparar()[:3]
    lento = casos[1].entrada
    vistos: dict[str, int] = {}

    def contestar(cuerpo, n):
        entrada = cuerpo["messages"][1]["content"]
        vistos[entrada] = vistos.get(entrada, 0) + 1
        if entrada == lento and vistos[entrada] == 1:
            return 429, {"error": {"message": "rate limited"}}
        if entrada == lento and vistos[entrada] == 2:
            return 200, servidor.de_modelo("esto no es JSON", tokens=(1000, 10))
        return 200, servidor.de_modelo(correctas[entrada])

    servidor.contestar = contestar
    informe = ejecutar_tarea(cliente, tarea, "anthropic/claude-haiku-4-5", casos=casos, concurrencia=1)
    assert informe.resultado["aciertos"] == 3
    assert vistos[lento] == 3
    # El 429 no trae tokens; el intento con JSON inválido sí, y se suma al bueno.
    assert informe.uso.tokens_entrada == 3 * 1200 + 1000
    assert informe.uso.tokens_salida == 3 * 150 + 10
    registro = next(c for c in informe.registros if c.id == casos[1].id)
    assert registro.uso is not None and registro.uso.tokens_entrada == 2200


def test_modo_barato_recorta_casos_y_lo_dice(servidor, cliente, tareas):
    tarea = tareas["clasificar-facturas"]
    correctas = correcta_por_entrada(tarea)
    servidor.contestar = lambda cuerpo, n: (
        200,
        servidor.de_modelo(correctas[cuerpo["messages"][1]["content"]]),
    )
    casos = tarea.preparar()[:5]
    r = ejecutar_tarea(cliente, tarea, "anthropic/claude-haiku-4-5", casos=casos, modo_barato=True).resultado
    assert r["casos"] == 5
    assert r["tarea_nombre"] == f"{tarea.nombre} (muestra de 5 casos)"
    assert len(servidor.peticiones) == 5


def test_respuesta_con_vallas_y_claves_parecidas_se_rescata(servidor, cliente, tareas):
    tarea = tareas["clasificar-facturas"]
    caso = tarea.preparar()[10]  # factura-11: alquiler con retención
    texto = (
        "Aquí tienes la factura:\n```json\n"
        '{"proveedor": "Inmobiliaria Las Maromas S.L.", "numero_factura": "2026-09-A14", "fecha_factura": "2026-09-01", '
        '"base_imponible": 2400, "cuota_iva": 504, "importe_total": "2.448,00 €", "fecha_vencimiento": "05/09/2026", '
        '"cuenta_sugerida": "621", "duplicada": "no"}\n```\nEspero que te sirva.'
    )
    servidor.contestar = lambda cuerpo, n: (200, servidor.de_modelo(texto))
    informe = ejecutar_tarea(cliente, tarea, "anthropic/claude-haiku-4-5", casos=[caso])
    assert informe.resultado["aciertos"] == 1
    assert informe.registros[0].respuesta["total"] == "2.448,00 €"


def test_llamar_sin_esquema_devuelve_el_texto(servidor, cliente):
    servidor.contestar = lambda cuerpo, n: (200, servidor.de_modelo("hola"))
    r = cliente.llamar("anthropic/claude-haiku-4-5", "claude-haiku-4-5", Peticion(system="s", user="u"))
    assert r.datos == {"texto": "hola"}
    assert r.uso.coste_eur == (1200 * 0.9 + 150 * 4.5) / 1_000_000


def test_contenido_en_partes(servidor, cliente):
    servidor.contestar = lambda cuerpo, n: (
        200,
        {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "text", "text": '{"a":'},
                            {"type": "text", "text": "1}"},
                        ]
                    }
                }
            ]
        },
    )
    r = cliente.llamar("x/y", "y", Peticion(system="s", user="u", esquema={"type": "object", "required": ["a"]}))
    assert r.datos == {"a": 1}
    assert r.uso.tokens_entrada == 0
    assert r.modelo == "x/y"


def test_cli_ejecutar_de_punta_a_punta(servidor, raiz, tmp_path, tareas):
    tarea = tareas["redactar-recordatorio"]
    correctas = correcta_por_entrada(tarea)
    servidor.contestar = lambda cuerpo, n: (
        200,
        servidor.de_modelo(correctas[cuerpo["messages"][1]["content"]]),
    )
    env = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "CLAVE_DE_PRUEBA": "secreta",
        "NO_PROXY": "127.0.0.1",
    }
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "kit_pyme",
            "ejecutar",
            "--tarea",
            "redactar-recordatorio",
            "--endpoint",
            servidor.url,
            "--modelo",
            "anthropic/claude-haiku-4-5",
            "--clave-env",
            "CLAVE_DE_PRUEBA",
            "--salida",
            str(tmp_path),
        ],
        cwd=raiz,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    assert r.returncode == 0, r.stderr + r.stdout
    resultado = json.loads((tmp_path / "resultado.json").read_text(encoding="utf-8"))
    assert list(resultado) == CLAVES_RESULTADO
    assert (resultado["casos"], resultado["aciertos"]) == (10, 10)
    assert resultado["modelo"] == "anthropic/claude-haiku-4-5"
    assert resultado["coste_eur"] == 0.0176
    detalle = json.loads((tmp_path / "detalle.json").read_text(encoding="utf-8"))
    assert detalle["modelo_pedido"] == "anthropic/claude-haiku-4-5"
    assert len(detalle["casos"]) == 10
    assert servidor.peticiones[0]["cabeceras"]["authorization"] == "Bearer secreta"
    assert re.search(r"Veredicto\s+lo-usaria-el-lunes", r.stdout)


def test_cli_ejecutar_con_4xx_sale_con_codigo_3(servidor, raiz):
    servidor.contestar = lambda cuerpo, n: (401, {"error": {"message": "invalid api key"}})
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "NO_PROXY": "127.0.0.1"}
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "kit_pyme",
            "ejecutar",
            "--tarea",
            "resumir-correos",
            "--endpoint",
            servidor.url,
            "--modelo",
            "openai/gpt-6",
            "--concurrencia",
            "1",
        ],
        cwd=raiz,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    assert r.returncode == 3
    assert "respondió 401 para openai/gpt-6" in r.stderr
    assert len(servidor.peticiones) == 1
    assert not (Path(raiz) / "resultado.json").exists()
