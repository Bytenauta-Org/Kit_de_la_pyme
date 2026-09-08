"""Utilidades de normalización con las que compara la puntuación.

Son la traducción, función a función, de ``src/pruebas/puntuar.ts`` (líneas 24-84 y
236-242) del blog. Todas las comparaciones de ``puntuacion`` pasan por aquí, así que la
mitad de la paridad entre el kit y el blog está en este módulo.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

from kit_pyme import javascript as js

_DIACRITICOS_RE = re.compile("[" + chr(0x0300) + "-" + chr(0x036F) + "]")  # NFD: marcas
_NO_ALFANUMERICO_RE = re.compile("[^A-Z0-9]")
_EUROS_Y_ESPACIOS_RE = re.compile("[€" + js.CLASE_ESPACIOS[1:-1] + "]")
_COMA_DECIMAL_RE = re.compile(r",[0-9]{1,2}\Z")
_PUNTO_DECIMAL_RE = re.compile(r"\.[0-9]{1,2}\Z")
_FECHA_ISO_RE = re.compile(r"([0-9]{4})-([0-9]{1,2})-([0-9]{1,2})")
_FECHA_ES_RE = re.compile(r"([0-9]{1,2})[/.-]([0-9]{1,2})[/.-]([0-9]{4})")
_FECHA_LETRAS_RE = re.compile(r"([0-9]{1,2}) de ([a-z]+) de ([0-9]{4})")
_MILLARES_RE = re.compile(r"\B(?=([0-9]{3})+(?![0-9]))")
_ETIQUETA_RE = re.compile(r"([a-z]+)-([0-9]+)\Z", re.IGNORECASE)

MESES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

_NOMBRES_ETIQUETA = {
    "pedido": "Pedido",
    "correo": "Correo",
    "factura": "Factura",
    "recordatorio": "Recordatorio",
}


def texto(v: Any) -> str:
    """Convierte cualquier valor a cadena como lo hace el blog (``texto()`` en puntuar.ts).

    Args:
        v: Cualquier valor JSON.

    Returns:
        La cadena tal cual; ``""`` para ``None``; el JSON compacto para diccionarios y
        listas; ``"true"``/``"false"`` para booleanos; el número como lo escribe JavaScript.
    """
    if isinstance(v, str):
        return v
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, dict | list | tuple):
        return js.json_texto(v)
    if isinstance(v, int | float):
        return js.texto_de_numero(v)
    return str(v)


def normalizar_texto(v: Any) -> str:
    r"""Minúsculas, sin acentos, espacios simples y sin espacios en los extremos.

    Args:
        v: Cualquier valor; pasa antes por ``texto``.

    Returns:
        ``"  Reclamación   URGENTE\\n\\tya "`` → ``"reclamacion urgente ya"``.
    """
    t = texto(v).lower()
    t = unicodedata.normalize("NFD", t)
    t = _DIACRITICOS_RE.sub("", t)
    return js.recortar(js.colapsar_espacios(t))


def normalizar_referencia(v: Any) -> str:
    """Solo letras y números en mayúsculas: ``"cons atun-ol_120."`` → ``"CONSATUNOL120"``.

    No corrige el ``0`` por ``O`` del OCR: eso es trabajo del modelo, no del corrector.

    Args:
        v: Cualquier valor; pasa antes por ``texto``.

    Returns:
        La referencia normalizada.
    """
    return _NO_ALFANUMERICO_RE.sub("", texto(v).upper())


def leer_numero(v: Any) -> int | float | None:
    """Lee un número escrito a la española o a la inglesa.

    ``"1.234,56"``, ``"1234.56"``, ``"1 234,56 €"`` → 1234.56. Un número ya numérico se
    devuelve tal cual si es finito. Cualquier otro tipo (booleanos incluidos) es ``None``.

    Args:
        v: Cualquier valor JSON.

    Returns:
        El número, o ``None`` si no hay número legible.
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return v if math.isfinite(v) else None
    if not isinstance(v, str):
        return None
    s = _EUROS_Y_ESPACIOS_RE.sub("", v)
    if not s:
        return None
    if _COMA_DECIMAL_RE.search(s):
        s = s.replace(".", "").replace(",", ".", 1)
    elif _PUNTO_DECIMAL_RE.search(s):
        s = s.replace(",", "")
    else:
        s = s.replace(".", "").replace(",", "")
    return js.numero_de_texto(s)


def leer_fecha(v: Any) -> str | None:
    """Lee una fecha en cualquiera de los formatos habituales y la devuelve como AAAA-MM-DD.

    Acepta ``07/09/2026``, ``7-9-2026``, ``2026-09-07`` y ``7 de septiembre de 2026``.
    Si hay varias, gana la primera en formato ISO. No valida el calendario.

    Args:
        v: Cualquier valor; pasa antes por ``normalizar_texto``.

    Returns:
        La fecha como ``AAAA-MM-DD``, o ``None`` si no se reconoce ninguna.
    """
    s = normalizar_texto(v)
    m = _FECHA_ISO_RE.search(s)
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    m = _FECHA_ES_RE.search(s)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    m = _FECHA_LETRAS_RE.search(s)
    if m and m.group(2) in MESES:
        mes = MESES.index(m.group(2)) + 1
        return f"{m.group(3)}-{str(mes).zfill(2)}-{m.group(1).zfill(2)}"
    return None


def formatear_euros(n: float) -> str:
    """Escribe un importe como en los textos de fallo: ``4312.6`` → ``"4.312,60 €"``.

    Args:
        n: Importe en euros.

    Returns:
        El importe con dos decimales, coma decimal, punto de millar y el símbolo del euro.
    """
    s = js.a_fijo(n, 2).replace(".", ",", 1)
    return _MILLARES_RE.sub(".", s) + " €"


def leer_booleano(v: Any) -> bool | None:
    """Lee un booleano escrito de cualquier manera razonable.

    ``true``, ``si``, ``duplicada``, ``yes`` y ``1`` son verdadero; ``false``, ``no``, ``0``
    y el vacío (también el campo ausente) son falso; lo demás es ``None``.

    Args:
        v: Cualquier valor JSON.

    Returns:
        ``True``, ``False`` o ``None`` si no se entiende.
    """
    if isinstance(v, bool):
        return v
    s = normalizar_texto(v)
    if s in ("true", "si", "sí", "duplicada", "yes", "1"):
        return True
    if s in ("false", "no", "0", ""):
        return False
    return None


def objeto(v: Any) -> dict[str, Any]:
    """Devuelve el valor si es un objeto JSON y ``{}`` en cualquier otro caso.

    Args:
        v: Cualquier valor JSON.

    Returns:
        El diccionario, o uno vacío.
    """
    return v if isinstance(v, dict) else {}


def lista(v: Any) -> list[Any]:
    """Devuelve el valor si es una lista y ``[]`` en cualquier otro caso.

    Args:
        v: Cualquier valor JSON.

    Returns:
        La lista, o una vacía.
    """
    return v if isinstance(v, list) else []


def etiqueta(id_caso: str) -> str:
    """Etiqueta legible de un caso: ``"pedido-06"`` → ``"Pedido 06"``; ``"p01"`` → ``"p01"``.

    Args:
        id_caso: Identificador del caso.

    Returns:
        La etiqueta que encabeza los textos de fallo.
    """
    m = _ETIQUETA_RE.match(id_caso)
    if not m:
        return id_caso
    return f"{_NOMBRES_ETIQUETA.get(m.group(1), m.group(1))} {m.group(2)}"
