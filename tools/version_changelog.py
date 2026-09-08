"""Lee la versión vigente del kit de datos en ``CHANGELOG.md``.

El kit de datos sigue versionado semántico y el CHANGELOG el formato *Keep a Changelog*:
cada versión publicada es un encabezado ``## [1.0.0] - 2026-09-08`` (también valen
``## 1.0.0 (2026-09-08)`` y ``## v1.0.0``). La primera sección con número de versión es
la vigente; la sección ``[Sin publicar]`` / ``[Unreleased]`` se ignora.

Lo usa ``.github/workflows/release.yml`` para etiquetar ``vX.Y.Z`` y publicar la release
con las notas de esa sección, y sirve para comprobar a mano que una etiqueta cuadra.

Uso::

    python tools/version_changelog.py                     # imprime «1.0.0»
    python tools/version_changelog.py --github-output     # version=1.0.0 y fecha=2026-09-08
    python tools/version_changelog.py --notas notas.md    # guarda las notas de la sección
    python tools/version_changelog.py --comprobar v1.0.0  # código 1 si no coincide
"""

from __future__ import annotations

import argparse
import dataclasses
import pathlib
import re
import sys
from collections.abc import Sequence

#: Encabezado de sección con versión: ``## [1.0.0] - 2026-09-08``, ``## 1.0.0 (2026-09-08)``…
_ENCABEZADO = re.compile(
    r"^##\s+\[?v?(?P<version>\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\]?"
    r"(?:\s*[-–—(]\s*(?P<fecha>\d{4}-\d{2}-\d{2})\)?)?\s*$"
)

#: Definición de enlace al pie (``[1.0.0]: https://…``): no forma parte de las notas.
_REFERENCIA = re.compile(r"^\[[^\]]+\]:\s+\S+")


@dataclasses.dataclass(frozen=True)
class Version:
    """Una sección de versión del CHANGELOG.

    Attributes:
        numero: La versión sin la «v» (``1.0.0``).
        fecha: La fecha ``AAAA-MM-DD`` del encabezado, o ``None`` si no la lleva.
        notas: El cuerpo de la sección en Markdown, sin las definiciones de enlace.
    """

    numero: str
    fecha: str | None
    notas: str


def leer_versiones(texto: str) -> list[Version]:
    """Devuelve las secciones con número de versión, de la más reciente a la más antigua.

    Args:
        texto: Contenido de ``CHANGELOG.md``.

    Returns:
        Las versiones en el orden del fichero (Keep a Changelog las pone de nueva a vieja).
    """
    versiones: list[Version] = []
    actual: tuple[str, str | None] | None = None
    cuerpo: list[str] = []

    def cerrar() -> None:
        if actual is not None:
            versiones.append(Version(actual[0], actual[1], _limpiar(cuerpo)))

    for linea in texto.splitlines():
        if linea.startswith("## "):
            cerrar()
            coincidencia = _ENCABEZADO.match(linea)
            actual = (coincidencia["version"], coincidencia["fecha"]) if coincidencia else None
            cuerpo = []
        elif actual is not None:
            cuerpo.append(linea)
    cerrar()
    return versiones


def _limpiar(lineas: Sequence[str]) -> str:
    sin_referencias = [linea for linea in lineas if not _REFERENCIA.match(linea)]
    return "\n".join(sin_referencias).strip("\n")


def version_vigente(texto: str) -> Version:
    """Devuelve la primera versión del CHANGELOG (la vigente).

    Args:
        texto: Contenido de ``CHANGELOG.md``.

    Returns:
        La versión vigente.

    Raises:
        ValueError: Si el CHANGELOG no tiene ninguna sección ``## [X.Y.Z]``.
    """
    versiones = leer_versiones(texto)
    if not versiones:
        raise ValueError("CHANGELOG.md no tiene ninguna sección «## [X.Y.Z] - AAAA-MM-DD»")
    return versiones[0]


def _argumentos(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="version_changelog",
        description="Lee la versión vigente del kit de datos en CHANGELOG.md.",
    )
    parser.add_argument(
        "changelog",
        nargs="?",
        default="CHANGELOG.md",
        type=pathlib.Path,
        help="ruta del CHANGELOG (por defecto, CHANGELOG.md)",
    )
    parser.add_argument(
        "--github-output",
        action="store_true",
        help="imprime «version=…» y «fecha=…» para volcarlos en $GITHUB_OUTPUT",
    )
    parser.add_argument(
        "--notas",
        type=pathlib.Path,
        metavar="FICHERO",
        help="guarda las notas de la versión vigente en FICHERO (Markdown)",
    )
    parser.add_argument(
        "--comprobar",
        metavar="VERSION",
        help="sale con código 1 si la versión vigente no es VERSION (con o sin «v»)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada de la línea de órdenes.

    Args:
        argv: Argumentos sin el nombre del programa; ``None`` para usar ``sys.argv``.

    Returns:
        El código de salida.
    """
    args = _argumentos(argv)
    try:
        vigente = version_vigente(args.changelog.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"ERROR: no existe {args.changelog}", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    if args.notas is not None:
        notas = vigente.notas or f"Versión {vigente.numero} del kit de datos."
        args.notas.write_text(notas + "\n", encoding="utf-8")

    if args.comprobar is not None:
        esperada = args.comprobar.strip().removeprefix("v")
        if esperada != vigente.numero:
            print(
                f"ERROR: el CHANGELOG está en {vigente.numero} y se esperaba {esperada}",
                file=sys.stderr,
            )
            return 1

    if args.github_output:
        print(f"version={vigente.numero}")
        print(f"fecha={vigente.fecha or ''}")
    else:
        print(vigente.numero)
    return 0


if __name__ == "__main__":
    sys.exit(main())
