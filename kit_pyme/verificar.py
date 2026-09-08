"""Comprueba que los datos del kit son los publicados: ``datos/CHECKSUMS.sha256`` y los prompts.

Los datos no cambian entre semanas para que las cifras sean comparables. ``verificar``
recalcula el sha256 de cada fichero de datos, avisa de los que faltan o han cambiado, de
los que sobran en las cinco carpetas de datos, y de los prompts cuyo sha256 no coincide
con el de ``tarea.json``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from kit_pyme.tareas import cargar_tarea, ids_tareas

#: Carpetas de datos que tienen que contener exactamente los ficheros de la lista.
CARPETAS_DATOS = ("pedidos", "correos", "contrato", "facturas", "cobros")

#: Nombre del fichero de sumas, en formato de ``sha256sum``.
FICHERO_CHECKSUMS = "CHECKSUMS.sha256"


def sha256_fichero(ruta: Path) -> str:
    """El sha256 hexadecimal de un fichero, byte a byte.

    Args:
        ruta: Ruta del fichero.

    Returns:
        El hash en hexadecimal.
    """
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 16), b""):
            h.update(bloque)
    return h.hexdigest()


def sha256_texto(texto: str) -> str:
    """El sha256 hexadecimal de un texto en UTF-8.

    Args:
        texto: El texto.

    Returns:
        El hash en hexadecimal.
    """
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def ficheros_de_datos(raiz: Path) -> list[Path]:
    """Los ficheros de las cinco carpetas de datos, ordenados por ruta.

    Args:
        raiz: Raíz del kit.

    Returns:
        Rutas relativas a ``datos/``.
    """
    datos = raiz / "datos"
    encontrados: list[Path] = []
    for carpeta in CARPETAS_DATOS:
        if (datos / carpeta).is_dir():
            encontrados.extend(p.relative_to(datos) for p in (datos / carpeta).rglob("*") if p.is_file())
    return sorted(encontrados, key=lambda p: p.as_posix())


def leer_checksums(ruta: Path) -> dict[str, str]:
    """Lee un fichero en formato ``sha256sum`` («hash  ruta», una por línea).

    Args:
        ruta: Ruta del fichero.

    Returns:
        Ruta relativa → hash.

    Raises:
        ValueError: Si una línea no tiene el formato esperado.
    """
    sumas: dict[str, str] = {}
    with open(ruta, encoding="utf-8") as f:
        for n, linea in enumerate(f, start=1):
            linea = linea.rstrip("\r\n")
            if not linea or linea.startswith("#"):
                continue
            partes = linea.split("  ", 1)
            if len(partes) != 2 or len(partes[0]) != 64:
                raise ValueError(f"{ruta}:{n}: no tiene el formato «hash  ruta»")
            sumas[partes[1].lstrip("*")] = partes[0].lower()
    return sumas


def generar_checksums(raiz: Path) -> str:
    """Genera el contenido de ``CHECKSUMS.sha256`` con los ficheros de datos actuales.

    Args:
        raiz: Raíz del kit.

    Returns:
        El texto del fichero (una línea por fichero, ordenadas por ruta, LF).
    """
    datos = raiz / "datos"
    lineas = [f"{sha256_fichero(datos / p)}  {p.as_posix()}" for p in ficheros_de_datos(raiz)]
    return "\n".join(lineas) + "\n"


def verificar(raiz: Path) -> list[str]:
    """Comprueba los datos y los prompts del kit.

    Args:
        raiz: Raíz del kit.

    Returns:
        Lista de problemas en texto; vacía si todo está como se publicó.
    """
    problemas: list[str] = []
    datos = raiz / "datos"
    ruta_sumas = datos / FICHERO_CHECKSUMS
    if not ruta_sumas.is_file():
        return [f"falta {ruta_sumas.relative_to(raiz).as_posix()}"]
    try:
        esperadas = leer_checksums(ruta_sumas)
    except ValueError as e:
        return [str(e)]
    presentes = {p.as_posix() for p in ficheros_de_datos(raiz)}
    for rel, esperado in esperadas.items():
        ruta = datos / rel
        if not ruta.is_file():
            problemas.append(f"falta datos/{rel}")
        elif sha256_fichero(ruta) != esperado:
            problemas.append(f"datos/{rel} ha cambiado (sha256 distinto del publicado)")
    for rel in sorted(presentes - set(esperadas)):
        problemas.append(f"datos/{rel} no está en {FICHERO_CHECKSUMS}: sobra o hay que versionar el kit")
    for id_tarea in ids_tareas(raiz):
        try:
            tarea = cargar_tarea(id_tarea, raiz)
        except (OSError, ValueError, KeyError) as e:
            problemas.append(f"tareas/{id_tarea}/tarea.json no se puede cargar: {e}")
            continue
        ruta_json = raiz / "tareas" / id_tarea / "tarea.json"
        esperados = json.loads(ruta_json.read_text(encoding="utf-8")).get("sha256") or {}
        if esperados.get("prompt") and sha256_texto(tarea.prompt) != esperados["prompt"]:
            problemas.append(f"tareas/{id_tarea}: el prompt compuesto no coincide con su sha256")
        if esperados.get("system") and sha256_texto(tarea.system) != esperados["system"]:
            problemas.append(f"tareas/{id_tarea}: el mensaje de sistema no coincide con su sha256")
    return problemas
