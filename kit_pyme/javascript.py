r"""Emulación de lo que hace JavaScript donde Python difiere.

El banco de pruebas del blog está escrito en TypeScript y corre en un Worker de
Cloudflare. Para que este paquete puntúe exactamente igual, hay que reproducir el
comportamiento de JavaScript en los puntos en los que Python se aparta: la clase ``\\s``
de sus expresiones regulares (incluye U+FEFF), ``String(n)`` para números,
``Number(s)`` para cadenas, ``Math.round`` (los .5 van hacia +∞) y ``toFixed``
(redondea el valor binario exacto, con los empates hacia arriba), y el
``JSON.stringify`` compacto.

Todas las tablas de ``tests/oro/resumen.json`` se generaron ejecutando el TypeScript
real; los tests de este módulo comparan contra ellas.
"""

from __future__ import annotations

import json
import math
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

#: Puntos de código que JavaScript trata como espacio en ``\s`` y en ``trim()``. Python no
#: incluye U+FEFF en ``str.isspace()`` ni en su ``\s``, y sí incluye U+001C-U+001F, que
#: JavaScript no. Se escriben como números para que no haya caracteres invisibles en el código.
CODIGOS_ESPACIO: tuple[int, ...] = (
    0x0009,
    0x000A,
    0x000B,
    0x000C,
    0x000D,
    0x0020,
    0x00A0,
    0x1680,
    *range(0x2000, 0x200B),
    0x2028,
    0x2029,
    0x202F,
    0x205F,
    0x3000,
    0xFEFF,
)

#: Los mismos caracteres, para ``str.strip``.
ESPACIOS = "".join(chr(c) for c in CODIGOS_ESPACIO)

#: La misma clase, lista para meterla en una expresión regular (equivale a ``\s`` de JS).
CLASE_ESPACIOS = "[" + "".join("\\u" + format(c, "04x") for c in CODIGOS_ESPACIO) + "]"

_ESPACIOS_RE = re.compile(CLASE_ESPACIOS + "+")

# Lo que acepta ``Number(cadena)``: un literal decimal con signo opcional, o hexadecimal,
# octal o binario sin signo. Nada de ``1_000``, ``Infinity`` (no es finito) ni texto suelto.
_DECIMAL_RE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")
_HEX_RE = re.compile(r"0[xX][0-9a-fA-F]+\Z")
_OCT_RE = re.compile(r"0[oO][0-7]+\Z")
_BIN_RE = re.compile(r"0[bB][01]+\Z")


def recortar(s: str) -> str:
    r"""Equivale a ``String.prototype.trim()``: quita los espacios de JavaScript por ambos lados.

    Args:
        s: Cadena a recortar.

    Returns:
        La cadena sin espacios (según la clase ``\\s`` de JavaScript) al principio ni al final.
    """
    return s.strip(ESPACIOS)


def colapsar_espacios(s: str, por: str = " ") -> str:
    r"""Equivale a ``s.replace(/\\s+/g, por)``.

    Args:
        s: Cadena de entrada.
        por: Texto que sustituye a cada racha de espacios.

    Returns:
        La cadena con cada racha de espacios de JavaScript sustituida por ``por``.
    """
    return _ESPACIOS_RE.sub(por, s)


def texto_de_numero(n: int | float) -> str:
    """Equivale a ``String(n)`` (algoritmo Number::toString de ECMAScript).

    JavaScript escribe ``1`` donde Python escribe ``1.0``, ``1e-7`` donde Python escribe
    ``1e-07`` y ``0.00001`` donde Python escribe ``1e-05``. Cambia a notación exponencial
    solo por debajo de 1e-6 y a partir de 1e21.

    Args:
        n: Número entero o de coma flotante (los booleanos se tratan aparte en ``texto``).

    Returns:
        El número escrito como lo escribiría JavaScript.
    """
    if isinstance(n, int) and not isinstance(n, bool) and abs(n) < 10**21:
        return str(n)
    x = float(n)
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    if x == 0:
        return "0"
    if x.is_integer() and abs(x) < 1e21:
        return str(int(x))
    signo = "-" if x < 0 else ""
    d = Decimal(repr(abs(x))).normalize()
    digitos = "".join(str(c) for c in d.as_tuple().digits)
    k = len(digitos)
    n_exp = k + int(d.as_tuple().exponent)
    if k <= n_exp <= 21:
        cuerpo = digitos + "0" * (n_exp - k)
    elif 0 < n_exp <= 21:
        cuerpo = digitos[:n_exp] + "." + digitos[n_exp:]
    elif -6 < n_exp <= 0:
        cuerpo = "0." + "0" * (-n_exp) + digitos
    else:
        exponente = n_exp - 1
        signo_exp = "+" if exponente >= 0 else "-"
        mantisa = digitos if k == 1 else digitos[0] + "." + digitos[1:]
        cuerpo = f"{mantisa}e{signo_exp}{abs(exponente)}"
    return signo + cuerpo


def numero_de_texto(s: str) -> float | None:
    """Equivale a ``Number(s)`` cuando el resultado es finito.

    Args:
        s: Cadena ya sin espacios (``leer_numero`` los quita antes).

    Returns:
        El número, o ``None`` si JavaScript devolvería ``NaN`` o un infinito.
    """
    if _DECIMAL_RE.match(s):
        try:
            valor = float(s)
        except ValueError:
            return None
        return valor if math.isfinite(valor) else None
    if _HEX_RE.match(s):
        return float(int(s[2:], 16))
    if _OCT_RE.match(s):
        return float(int(s[2:], 8))
    if _BIN_RE.match(s):
        return float(int(s[2:], 2))
    return None


def redondear(x: float) -> int:
    """Equivale a ``Math.round(x)``: el entero más cercano, con los .5 hacia +∞.

    ``round()`` de Python redondea los .5 al par y ``floor(x + 0.5)`` falla por precisión
    con valores como 0.49999999999999994; esta forma reproduce a JavaScript en ambos casos.

    Args:
        x: Número a redondear.

    Returns:
        El entero que devolvería JavaScript.
    """
    f = math.floor(x)
    return f if x - f < 0.5 else f + 1


def a_fijo(x: float, decimales: int) -> str:
    """Equivale a ``x.toFixed(decimales)`` para números normales (|x| < 1e21).

    JavaScript redondea el valor binario exacto del número, no su representación decimal:
    ``(1.005).toFixed(2)`` es ``"1.00"`` porque 1.005 se guarda como 1.00499999…, y
    ``(0.125).toFixed(2)`` es ``"0.13"`` porque el empate exacto va hacia arriba.
    ``Decimal(x)`` da ese valor exacto y ``ROUND_HALF_UP`` resuelve el empate igual.

    Args:
        x: Número a formatear.
        decimales: Cifras decimales (0 a 100).

    Returns:
        El número escrito con esos decimales, como lo escribiría JavaScript.
    """
    cuanto = Decimal(1).scaleb(-decimales)
    return format(Decimal(x).quantize(cuanto, rounding=ROUND_HALF_UP), "f")


def json_texto(v: Any) -> str:
    """Equivale a ``JSON.stringify(v)`` sin sangría.

    Sin espacios, con las claves en su orden de inserción, sin escapar los caracteres no
    ASCII y con los números escritos como los escribe JavaScript (``1`` y no ``1.0``).

    Args:
        v: Diccionario, lista, cadena, número, booleano o ``None``.

    Returns:
        El JSON compacto.
    """
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int | float):
        return "null" if not math.isfinite(float(v)) else texto_de_numero(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, dict):
        pares = (f"{json.dumps(str(k), ensure_ascii=False)}:{json_texto(x)}" for k, x in v.items())
        return "{" + ",".join(pares) + "}"
    if isinstance(v, list | tuple):
        return "[" + ",".join(json_texto(x) for x in v) + "]"
    return json.dumps(str(v), ensure_ascii=False)
