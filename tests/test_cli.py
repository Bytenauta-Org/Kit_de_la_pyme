"""La línea de órdenes, por subproceso: tareas, casos, prompt, puntuar y verificar."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from kit_pyme.tareas import ORDEN_TAREAS
from tests.conftest import ORO

CLAVES_RESULTADO = [
    "novedad_url",
    "modelo",
    "tarea",
    "tarea_nombre",
    "casos",
    "aciertos",
    "fallos",
    "segundos",
    "coste_eur",
    "veredicto",
    "nota",
]


def cli(raiz: Path, *args: str, entorno: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", **(entorno or {})}
    return subprocess.run(
        [sys.executable, "-m", "kit_pyme", *args],
        cwd=raiz,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )


def test_tareas(raiz):
    r = cli(raiz, "tareas")
    assert r.returncode == 0, r.stderr
    for t in ORDEN_TAREAS:
        assert t in r.stdout
    assert "Sacar las líneas de 20 pedidos" in r.stdout


def test_casos_jsonl_devuelve_las_entradas_exactas(raiz, tareas):
    r = cli(raiz, "casos", "buscar-en-contrato", "--jsonl")
    assert r.returncode == 0, r.stderr
    filas = [json.loads(ln) for ln in r.stdout.splitlines() if ln.strip()]
    assert [f["id"] for f in filas] == [c.id for c in tareas["buscar-en-contrato"].preparar()]
    assert filas[0]["entrada"] == tareas["buscar-en-contrato"].preparar()[0].entrada


def test_casos_texto_de_un_caso(raiz):
    r = cli(raiz, "casos", "clasificar-facturas", "--id", "factura-21")
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("===== factura-21 =====\n")
    assert "B38122941" in r.stdout


def test_casos_id_desconocido(raiz):
    r = cli(raiz, "casos", "clasificar-facturas", "--id", "factura-99")
    assert r.returncode == 1
    assert "factura-99" in r.stderr


def test_prompt_es_el_mensaje_de_sistema(raiz, tareas):
    r = cli(raiz, "prompt", "resumir-correos")
    assert r.returncode == 0, r.stderr
    assert r.stdout == tareas["resumir-correos"].system + "\n"


@pytest.mark.parametrize("id_tarea", ORDEN_TAREAS)
def test_puntuar_con_las_respuestas_verdaderas(raiz, tmp_path, id_tarea):
    r = cli(
        raiz,
        "puntuar",
        id_tarea,
        str(ORO / "respuestas-verdad" / f"{id_tarea}.jsonl"),
        "--modelo",
        "verdad",
        "--salida",
        str(tmp_path),
    )
    assert r.returncode == 0, r.stderr
    resultado = json.loads((tmp_path / "resultado.json").read_text(encoding="utf-8"))
    assert list(resultado) == CLAVES_RESULTADO
    assert resultado["aciertos"] == resultado["casos"]
    assert resultado["fallos"] == []
    assert resultado["modelo"] == "verdad"
    assert resultado["tarea"] == id_tarea
    assert resultado["coste_eur"] == 0
    assert resultado["veredicto"] == "lo-usaria-el-lunes"
    assert resultado["nota"].startswith(f"Acertó los {resultado['casos']} casos a 0,0 céntimos por caso")
    detalle = json.loads((tmp_path / "detalle.json").read_text(encoding="utf-8"))
    assert len(detalle["casos"]) == resultado["casos"]
    assert all(c["ok"] for c in detalle["casos"])
    assert f"Aciertos   {resultado['casos']} de {resultado['casos']}" in r.stdout


def test_puntuar_jsonl_incompleto_y_con_esquema_roto(raiz, tmp_path):
    lineas = [
        {
            "id": "correo-01",
            "respuesta": {
                "categoria": "reclamacion",
                "urgencia": "media",
                "accion": "",
                "resumen": "",
            },
        },
        {
            "id": "correo-02",
            "respuesta": {"categoria": "consulta"},
        },  # no cumple el esquema: sin respuesta
        {"id": "correo-03", "respuesta": None},  # null: llega al comparador y falla
        {
            "id": "correo-04",
            "respuesta": {"categoria": "spam", "urgencia": "baja", "accion": "", "resumen": ""},
        },
    ]
    jsonl = tmp_path / "r.jsonl"
    jsonl.write_text("\n".join(json.dumps(ln, ensure_ascii=False) for ln in lineas) + "\n", encoding="utf-8")
    r = cli(raiz, "puntuar", "resumir-correos", str(jsonl), "--json")
    assert r.returncode == 0, r.stderr
    resultado = json.loads(r.stdout)
    assert resultado["casos"] == 30
    assert resultado["aciertos"] == 1
    assert resultado["sin_respuesta"] == 28  # 26 sin línea + 1 con el esquema roto + 1 nulo
    assert "errores_servicio" not in resultado
    assert resultado["veredicto"] == "todavia-no"
    assert resultado["nota"].startswith("No devolvió una respuesta que se pudiera leer en 28 de 30 casos.")
    assert resultado["fallos"][0] == "Correo 02: el modelo no devolvió una respuesta válida"
    assert resultado["fallos"][1] == "Correo 03: no devolvió nada legible"


def test_puntuar_con_uso_y_segundos_declarados(raiz, tmp_path):
    filas = [
        json.loads(ln)
        for ln in (ORO / "respuestas-verdad" / "redactar-recordatorio.jsonl").read_text(encoding="utf-8").splitlines()
        if ln
    ]
    for f in filas:
        f["uso"] = {"tokens_entrada": 1200, "tokens_salida": 150, "coste_eur": 0.001755}
        f["segundos"] = 1.25
    jsonl = tmp_path / "r.jsonl"
    jsonl.write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in filas) + "\n", encoding="utf-8")
    r = cli(raiz, "puntuar", "redactar-recordatorio", str(jsonl), "--json")
    assert r.returncode == 0, r.stderr
    resultado = json.loads(r.stdout)
    assert resultado["coste_eur"] == 0.0176  # 10 × 0.001755 = 0.01755 → 0.0176 (Math.round)
    assert resultado["segundos"] == 12.5
    assert resultado["nota"].startswith("Acertó los 10 casos a 0,2 céntimos por caso")


def test_verificar(raiz):
    r = cli(raiz, "verificar")
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.startswith("OK")


def test_verificar_desde_otra_carpeta_con_raiz(raiz, tmp_path):
    r = cli(tmp_path, "--raiz", str(raiz), "verificar")
    assert r.returncode == 0, r.stdout + r.stderr


def test_tarea_desconocida(raiz):
    r = cli(raiz, "casos", "no-existe")
    assert r.returncode == 1
    assert "tarea desconocida" in r.stderr


def test_ejecutar_sin_endpoint_conocido(raiz):
    r = cli(raiz, "ejecutar", "--tarea", "resumir-correos", "--modelo", "ollama/llama")
    assert r.returncode == 1
    assert "--endpoint" in r.stderr


def test_ejecutar_con_clave_env_vacia(raiz):
    r = cli(
        raiz,
        "ejecutar",
        "--tarea",
        "resumir-correos",
        "--modelo",
        "openai/gpt-6",
        "--clave-env",
        "KIT_PYME_CLAVE_QUE_NO_EXISTE",
    )
    assert r.returncode == 1
    assert "KIT_PYME_CLAVE_QUE_NO_EXISTE" in r.stderr


def test_version(raiz):
    r = cli(raiz, "--version")
    assert r.returncode == 0
    assert "kit_pyme 1.0.0" in r.stdout
