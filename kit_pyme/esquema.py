"""Lo que pasa entre el texto que devuelve el modelo y el objeto que se puntúa.

Traduce ``conClavesExplicitas`` y ``normalizarClaves`` de ``src/pruebas/index.ts`` y
``extraerJson``, ``repararJson`` y ``validarContraEsquema`` de ``src/conector.ts`` (más
``escaparCrudos`` de ``src/json-crudo.ts``). En el blog, en modo directo, no viaja
``response_format``: el prompt pide JSON y este módulo lo saca del texto, aunque venga
entre vallas de código, con texto alrededor, cortado por ``max_tokens`` o con saltos de
línea crudos dentro de una cadena.
"""

from __future__ import annotations

import json
import re
from typing import Any

from kit_pyme import javascript as js

_VALLA_RE = re.compile("```(?:json)?" + js.CLASE_ESPACIOS + r"*([\s\S]*?)```", re.IGNORECASE)
_NO_ALFANUMERICO_RE = re.compile("[^a-z0-9]")


class ErrorJson(ValueError):
    """La respuesta del modelo no contiene un JSON legible."""


def _rechazar_constante(nombre: str) -> Any:
    """``JSON.parse`` no acepta ``NaN`` ni ``Infinity``; ``json.loads`` sí. Se rechazan.

    Args:
        nombre: La constante encontrada.

    Raises:
        ValueError: Siempre.
    """
    raise ValueError(f"constante no admitida en JSON: {nombre}")


def parsear_json(t: str) -> Any:
    """Equivale a ``JSON.parse(t)``.

    Args:
        t: Texto JSON.

    Returns:
        El valor parseado.

    Raises:
        ValueError: Si el texto no es JSON válido.
    """
    return json.loads(t, parse_constant=_rechazar_constante)


def con_claves_explicitas(prompt: str, esquema: dict[str, Any] | None) -> str:
    """Añade al prompt la línea que nombra las claves obligatorias del esquema.

    El prompt describe los campos con palabras («base imponible») y el esquema los pide
    con claves cortas («base»). Sin ``response_format`` el modelo contestaba con
    ``base_imponible`` y el esquema lo tumbaba tres veces por caso (08-09-2026). Es
    exactamente lo que envía el blog como mensaje de sistema.

    Args:
        prompt: Prompt de sistema de la tarea.
        esquema: JSON Schema de la respuesta.

    Returns:
        El prompt con la línea FORMATO al final, o tal cual si el esquema no tiene ``required``.
    """
    claves = list((esquema or {}).get("required") or [])
    if not claves:
        return prompt
    return (
        f"{prompt}\n\nFORMATO DE LA RESPUESTA: un solo objeto JSON con exactamente estas claves, "
        f"escritas así: {', '.join(claves)}. Sin otras claves, sin comentarios y sin texto "
        "antes ni después."
    )


def _forma(clave: str) -> str:
    return _NO_ALFANUMERICO_RE.sub("", clave.lower())


def normalizar_claves(datos: Any, esquema: dict[str, Any] | None) -> Any:
    """Rescata claves con nombre parecido (``base_imponible`` → ``base``) cuando falta la exacta.

    Las claves largas van primero (``vencimiento`` reclama ``fecha_vencimiento`` antes de que
    ``fecha`` lo vea). Solo se copia si hay exactamente una candidata; la original no se borra.

    Args:
        datos: Objeto devuelto por el modelo.
        esquema: JSON Schema con ``required``.

    Returns:
        Una copia del objeto con las claves requeridas rellenadas cuando se ha podido; el
        mismo valor si no es un objeto o el esquema no tiene ``required``.
    """
    requeridas = list((esquema or {}).get("required") or [])
    if not requeridas or not isinstance(datos, dict):
        return datos
    objeto = dict(datos)
    libres = [k for k in objeto if k not in requeridas]
    for clave in sorted(requeridas, key=len, reverse=True):
        if clave in objeto:
            continue
        candidatas = [k for k in libres if _forma(clave) in _forma(k)]
        if len(candidatas) == 1:
            objeto[clave] = objeto[candidatas[0]]
            libres.remove(candidatas[0])
    return objeto


def validar_contra_esquema(datos: Any, esquema: dict[str, Any]) -> list[str]:
    """Validación mínima, la misma que el blog: tipo de la raíz y ``required`` de primer nivel.

    Args:
        datos: Valor a validar.
        esquema: JSON Schema.

    Returns:
        Lista de fallos en texto; vacía si vale.
    """
    tipo = esquema.get("type")
    if tipo == "object":
        if not isinstance(datos, dict):
            return ["la raíz no es un objeto"]
        return [f"falta «{k}»" for k in esquema.get("required") or [] if k not in datos]
    if tipo == "array" and not isinstance(datos, list):
        return ["la raíz no es un array"]
    return []


def reparar_json(texto: str) -> str | None:
    """Cierra un JSON cortado a media respuesta (el modelo agotó ``max_tokens``).

    Recorre el texto llevando la cuenta de llaves, corchetes y comillas; anota cada cierre
    y lo que quedaba abierto en ese punto; después prueba a cortar en cada cierre, del último
    al primero (300 como mucho), cerrando lo pendiente. El primero que parsea es la respuesta.

    Args:
        texto: JSON posiblemente truncado, ya desde su primer ``{`` o ``[``.

    Returns:
        El JSON reparado, o ``None`` si no estaba truncado o no hay ningún elemento completo.
    """
    cierres: list[int] = []
    pendientes: list[list[str]] = []
    pila: list[str] = []
    en_cadena = False
    escape = False
    for i, c in enumerate(texto):
        if en_cadena:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                en_cadena = False
            continue
        if c == '"':
            en_cadena = True
        elif c == "{":
            pila.append("}")
        elif c == "[":
            pila.append("]")
        elif c in "}]":
            if pila:
                pila.pop()
            cierres.append(i)
            pendientes.append(list(pila))
    if not pila:
        return None
    tope = max(0, len(cierres) - 300)
    for k in range(len(cierres) - 1, tope - 1, -1):
        candidato = texto[: cierres[k] + 1] + "".join(reversed(pendientes[k]))
        try:
            parsear_json(candidato)
        except ValueError:
            continue
        return candidato
    return None


def escapar_crudos(texto: str) -> str:
    r"""Escapa los caracteres de control crudos que estén dentro de una cadena JSON.

    Un modelo puede cerrar bien el JSON y aun así escribir un salto de línea real dentro de
    una cadena. ``reparar_json`` no lo arregla (solo cierra lo abierto); esto sí.

    Args:
        texto: JSON entero pero con controles crudos.

    Returns:
        El mismo texto con ``\\n``, ``\\r``, ``\\t`` y ``\\u00XX`` dentro de las cadenas.
    """
    fuera: list[str] = []
    en_cadena = False
    escapando = False
    for c in texto:
        if escapando:
            fuera.append(c)
            escapando = False
            continue
        if en_cadena and c == "\\":
            fuera.append(c)
            escapando = True
            continue
        if c == '"':
            en_cadena = not en_cadena
            fuera.append(c)
            continue
        if en_cadena and ord(c) < 0x20:
            if c == "\n":
                fuera.append("\\n")
            elif c == "\r":
                fuera.append("\\r")
            elif c == "\t":
                fuera.append("\\t")
            else:
                fuera.append(f"\\u{ord(c):04x}")
            continue
        fuera.append(c)
    return "".join(fuera)


def extraer_json(texto: str) -> Any:
    """Quita vallas de código y busca el primer objeto o array JSON del texto.

    Args:
        texto: Lo que ha contestado el modelo.

    Returns:
        El valor JSON.

    Raises:
        ErrorJson: Si no hay JSON o no se puede reparar.
    """
    t = js.recortar(texto)
    valla = _VALLA_RE.search(t)
    if valla:
        t = js.recortar(valla.group(1))
    try:
        return parsear_json(t)
    except ValueError:
        pass
    posiciones = [p for p in (t.find("{"), t.find("[")) if p != -1]
    if not posiciones:
        raise ErrorJson("La respuesta no contiene JSON")
    desde_inicio = t[min(posiciones) :]
    fin = max(desde_inicio.rfind("}"), desde_inicio.rfind("]"))
    if fin > 0:
        try:
            return parsear_json(desde_inicio[: fin + 1])
        except ValueError:
            pass
    reparado = reparar_json(desde_inicio)
    if reparado:
        try:
            return parsear_json(reparado)
        except ValueError:
            pass
    for candidato in (desde_inicio[: fin + 1] if fin > 0 else desde_inicio, reparado or ""):
        if not candidato:
            continue
        try:
            return parsear_json(escapar_crudos(candidato))
        except ValueError:
            continue
    raise ErrorJson("La respuesta no es JSON válido ni reparable")
