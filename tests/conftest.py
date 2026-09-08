"""Fixtures comunes: la raíz del kit, las tareas cargadas y los oros del TypeScript.

Los oros (``tests/oro/``) se generaron ejecutando el código real del blog
(``src/pruebas/*.ts`` y ``src/conector.ts``) sobre los mismos datos: prompts y entradas
(sha256), respuestas correctas, 112 respuestas trucadas con su texto de fallo exacto, y
tablas de cada utilidad. Cualquier diferencia entre el Python y esas tablas es un fallo de
paridad, no una opinión.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from kit_pyme.puntuacion import AUSENTE
from kit_pyme.tareas import Tarea, cargar_tareas

RAIZ = Path(__file__).resolve().parent.parent
ORO = Path(__file__).resolve().parent / "oro"


def leer_oro(nombre: str) -> Any:
    with open(ORO / nombre, encoding="utf-8") as f:
        return json.load(f)


def respuestas_verdad(id_tarea: str) -> list[dict[str, Any]]:
    """Las respuestas correctas de una tarea, una por línea, como las escribió el TypeScript."""
    filas = []
    with open(ORO / "respuestas-verdad" / f"{id_tarea}.jsonl", encoding="utf-8") as f:
        for linea in f:
            if linea.strip():
                filas.append(json.loads(linea))
    return filas


def sin_undefined(v: Any) -> Any:
    """En los oros, ``"<undefined>"`` es el ``undefined`` de JavaScript."""
    return None if v == "<undefined>" else v


def respuesta_o_ausente(entrada: dict[str, Any]) -> Any:
    """En ``fallos-negativos.json`` la clave ``respuesta`` falta cuando era ``undefined``."""
    return entrada["respuesta"] if "respuesta" in entrada else AUSENTE


@pytest.fixture(scope="session")
def raiz() -> Path:
    return RAIZ


@pytest.fixture(scope="session")
def resumen() -> dict[str, Any]:
    return leer_oro("resumen.json")


@pytest.fixture(scope="session")
def negativos() -> list[dict[str, Any]]:
    return leer_oro("fallos-negativos.json")


@pytest.fixture(scope="session")
def tareas() -> dict[str, Tarea]:
    return {t.id: t for t in cargar_tareas(RAIZ)}


#: Carpetas que están en el árbol de trabajo pero no en el repositorio: cachés de
#: herramientas, entornos virtuales, empaquetado y restos de npx.
CARPETAS_AJENAS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "build",
        "dist",
        "env",
        "node_modules",
        "venv",
    }
)


def markdown_del_repositorio() -> list[Path]:
    """Todos los Markdown del kit, en orden y sin los de las carpetas de trabajo.

    Dos pruebas recorren el repositorio entero buscando ``*.md``: la de los enlaces internos
    y la de los diagramas. Sin filtrar, ``.pytest_cache/README.md`` entraba en la lista, así
    que el número de pruebas dependía de si pytest ya se había ejecutado antes en esa copia
    y no coincidía con el que dice la documentación.

    Returns:
        Las rutas absolutas de los Markdown versionados, ordenadas.
    """
    return sorted(
        ruta
        for ruta in RAIZ.rglob("*.md")
        if not any(parte in CARPETAS_AJENAS or parte.endswith(".egg-info") for parte in ruta.parts)
    )
