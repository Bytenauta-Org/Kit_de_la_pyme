"""Comprueba (o regenera) ``datos/CHECKSUMS.sha256``, el sello de la versión de los datos.

El fichero tiene el formato de ``sha256sum``: una línea por fichero, ``<sha256>  <ruta>`` con la
ruta relativa a ``datos/`` y dos espacios. Además de comparar hashes, el script avisa de ficheros
que faltan y de ficheros que sobran en las cinco carpetas de datos, porque cualquiera de las dos
cosas cambia lo que se le da al modelo y las cifras dejan de ser comparables con las del blog.

Uso::

    python tools/verificar_checksums.py             # comprueba datos/ del repositorio
    python tools/verificar_checksums.py --verboso   # además, una línea por fichero correcto
    python tools/verificar_checksums.py --escribir  # regenera el sello (solo al subir de versión)

Código de salida: 0 si todo cuadra, 1 si hay discrepancias, 2 si no se puede leer algo.
Solo usa la biblioteca estándar (Python 3.11 o posterior).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

CARPETAS: tuple[str, ...] = ("pedidos", "correos", "contrato", "facturas", "cobros")
"""Las cinco carpetas de datos, en el orden de las tareas."""

FICHERO_CHECKSUMS = "CHECKSUMS.sha256"
DATOS_POR_DEFECTO = Path(__file__).resolve().parent.parent / "datos"

_LINEA = re.compile(r"^([0-9a-fA-F]{64}) [ *](.+)$")
_TROZO = 1 << 16


@dataclass
class Informe:
    """Resultado de comparar los datos con ``CHECKSUMS.sha256``.

    Attributes:
        correctos: Rutas cuyo hash coincide.
        incorrectos: Parejas ``(ruta, hash_obtenido)`` cuyo hash no coincide.
        ausentes: Rutas que están en la lista pero no en el disco.
        sobrantes: Rutas que están en las carpetas de datos pero no en la lista.
        malformadas: Números de línea del fichero de checksums que no se entienden.
    """

    correctos: list[str] = field(default_factory=list)
    incorrectos: list[tuple[str, str]] = field(default_factory=list)
    ausentes: list[str] = field(default_factory=list)
    sobrantes: list[str] = field(default_factory=list)
    malformadas: list[int] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True si no hay ninguna discrepancia."""
        return not (self.incorrectos or self.ausentes or self.sobrantes or self.malformadas)


def sha256_de(ruta: Path) -> str:
    """Calcula el SHA-256 de un fichero leyéndolo por trozos.

    Args:
        ruta: Fichero a resumir.

    Returns:
        El hash en hexadecimal, en minúsculas.
    """
    resumen = hashlib.sha256()
    with ruta.open("rb") as fichero:
        for trozo in iter(lambda: fichero.read(_TROZO), b""):
            resumen.update(trozo)
    return resumen.hexdigest()


def ficheros_de_datos(datos: Path) -> list[str]:
    """Lista los ficheros que hay en las cinco carpetas de datos.

    Args:
        datos: Carpeta ``datos/``.

    Returns:
        Rutas relativas a ``datos`` con barras ``/``, carpeta a carpeta en el orden de
        ``CARPETAS`` y alfabéticas dentro de cada una. Es el orden del fichero de checksums.
    """
    rutas: list[str] = []
    for carpeta in CARPETAS:
        base = datos / carpeta
        if not base.is_dir():
            continue
        relativas = (p.relative_to(datos).as_posix() for p in base.rglob("*") if p.is_file())
        rutas.extend(sorted(relativas))
    return rutas


def leer_checksums(ruta: Path) -> tuple[dict[str, str], list[int]]:
    """Lee un fichero con el formato de ``sha256sum``.

    Args:
        ruta: El ``CHECKSUMS.sha256``.

    Returns:
        Un diccionario ``ruta relativa -> hash`` (rutas con ``/``, hash en minúsculas) y la lista
        de números de línea que no siguen el formato. Las líneas vacías y los comentarios ``#`` se
        ignoran.
    """
    esperados: dict[str, str] = {}
    malformadas: list[int] = []
    for numero, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), start=1):
        if not linea.strip() or linea.startswith("#"):
            continue
        casa = _LINEA.match(linea)
        if not casa:
            malformadas.append(numero)
            continue
        esperados[casa.group(2).replace("\\", "/").removeprefix("./")] = casa.group(1).lower()
    return esperados, malformadas


def generar(datos: Path) -> str:
    """Compone el texto de ``CHECKSUMS.sha256`` para los datos que hay ahora.

    Args:
        datos: Carpeta ``datos/``.

    Returns:
        Una línea ``<sha256>  <ruta>`` por fichero, con salto de línea final.
    """
    return "".join(f"{sha256_de(datos / ruta)}  {ruta}\n" for ruta in ficheros_de_datos(datos))


def verificar(datos: Path) -> Informe:
    """Compara los ficheros de datos con ``CHECKSUMS.sha256``.

    Args:
        datos: Carpeta ``datos/``, con el fichero de checksums y las cinco carpetas.

    Returns:
        El informe con correctos, incorrectos, ausentes, sobrantes y líneas malformadas.

    Raises:
        FileNotFoundError: Si no existe el fichero de checksums.
    """
    esperados, malformadas = leer_checksums(datos / FICHERO_CHECKSUMS)
    informe = Informe(malformadas=malformadas)
    for ruta, esperado in esperados.items():
        fichero = datos / ruta
        if not fichero.is_file():
            informe.ausentes.append(ruta)
            continue
        obtenido = sha256_de(fichero)
        if obtenido == esperado:
            informe.correctos.append(ruta)
        else:
            informe.incorrectos.append((ruta, obtenido))
    informe.sobrantes = [ruta for ruta in ficheros_de_datos(datos) if ruta not in esperados]
    return informe


def _salida_utf8() -> None:
    """Escribe en UTF-8 aunque la consola esté en otra codificación (Windows)."""
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")


def _imprimir(informe: Informe, verboso: bool) -> None:
    """Escribe el informe por la salida estándar, una línea por incidencia."""
    if verboso:
        for ruta in informe.correctos:
            print(f"OK          {ruta}")
    for ruta, obtenido in informe.incorrectos:
        print(f"INCORRECTO  {ruta}  (obtenido {obtenido})")
    for ruta in informe.ausentes:
        print(f"AUSENTE     {ruta}")
    for ruta in informe.sobrantes:
        print(f"SOBRANTE    {ruta}  (no está en {FICHERO_CHECKSUMS})")
    for numero in informe.malformadas:
        print(f"MALFORMADA  {FICHERO_CHECKSUMS}:{numero}")
    listados = len(informe.correctos) + len(informe.incorrectos) + len(informe.ausentes)
    print(
        f"{listados} ficheros en {FICHERO_CHECKSUMS}: {len(informe.correctos)} correctos, "
        f"{len(informe.incorrectos)} incorrectos, {len(informe.ausentes)} ausentes, "
        f"{len(informe.sobrantes)} sobrantes, {len(informe.malformadas)} líneas malformadas."
    )


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada de la línea de órdenes.

    Args:
        argv: Argumentos sin el nombre del programa; ``None`` para usar ``sys.argv``.

    Returns:
        0 si todo cuadra, 1 si hay discrepancias, 2 si falta algo por leer.
    """
    parser = argparse.ArgumentParser(
        description="Comprueba que los datos del kit son los que sella CHECKSUMS.sha256.",
    )
    parser.add_argument(
        "--datos",
        type=Path,
        default=DATOS_POR_DEFECTO,
        help=f"carpeta de datos (por defecto {DATOS_POR_DEFECTO})",
    )
    parser.add_argument("--verboso", action="store_true", help="una línea por fichero correcto")
    parser.add_argument(
        "--escribir",
        action="store_true",
        help="regenera CHECKSUMS.sha256 con los datos actuales (solo al subir de versión)",
    )
    args = parser.parse_args(argv)
    _salida_utf8()
    datos: Path = args.datos
    if not datos.is_dir():
        print(f"No existe la carpeta de datos: {datos}", file=sys.stderr)
        return 2
    if args.escribir:
        texto = generar(datos)
        (datos / FICHERO_CHECKSUMS).write_bytes(texto.encode("utf-8"))
        print(
            f"Escrito {datos / FICHERO_CHECKSUMS} con {texto.count(chr(10))} ficheros. "
            "Recuerda subir la versión de los datos y anotarlo en CHANGELOG.md."
        )
        return 0
    try:
        informe = verificar(datos)
    except FileNotFoundError:
        print(f"No existe {datos / FICHERO_CHECKSUMS}", file=sys.stderr)
        return 2
    _imprimir(informe, args.verboso)
    if informe.ok:
        print("Los datos coinciden con la versión sellada.")
        return 0
    print("Los datos NO coinciden con la versión sellada.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
