"""Comprueba que los diagramas Mermaid de los Markdown del repositorio son válidos.

El README y las guías de ``docs/`` explican el kit con diagramas Mermaid. Un diagrama
roto no se ve en GitHub (sale un recuadro de error) y nadie lo nota hasta que alguien
lo abre. Este script lo detecta en la integración continua.

Hace dos comprobaciones, de menos a más:

1. **Chequeo mínimo**, sin dependencias: cada bloque ```` ```mermaid ```` tiene
   contenido, empieza por un tipo de diagrama conocido y, en los diagramas de flujo,
   los corchetes, llaves y paréntesis están equilibrados fuera de las comillas.
2. **Renderizado real** con ``mmdc`` (mermaid-cli), si está en el ``PATH`` o se pide
   con ``--npx``: cada bloque se convierte a SVG en un directorio temporal, así que
   cualquier error de sintaxis que Mermaid detecte hace fallar el script.

Uso::

    python tools/comprobar_mermaid.py                       # README.md y docs/*.md
    python tools/comprobar_mermaid.py --npx --sin-sandbox   # como en la CI
    python tools/comprobar_mermaid.py --sin-mmdc docs/*.md  # solo el chequeo mínimo

Código de salida: 0 si todos los diagramas son válidos, 1 si alguno falla y 2 si no
se encontró ningún fichero que comprobar.
"""

from __future__ import annotations

import argparse
import dataclasses
import glob
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Sequence

#: Versión de mermaid-cli que se usa con ``--npx``. Fijada para que la CI sea reproducible.
VERSION_MMDC = "11.17.0"

#: Ficheros que se comprueban cuando no se pasa ninguno.
FICHEROS_POR_DEFECTO = ("README.md", "docs/*.md")

#: Primer token de un diagrama Mermaid (sin los sufijos ``-beta`` y ``-vN``).
TIPOS_CONOCIDOS = frozenset(
    {
        "architecture",
        "block",
        "C4Component",
        "C4Container",
        "C4Context",
        "C4Deployment",
        "C4Dynamic",
        "classDiagram",
        "erDiagram",
        "flowchart",
        "gantt",
        "gitGraph",
        "graph",
        "journey",
        "kanban",
        "mindmap",
        "packet",
        "pie",
        "quadrantChart",
        "radar",
        "requirementDiagram",
        "sankey",
        "sequenceDiagram",
        "stateDiagram",
        "timeline",
        "treemap",
        "xychart",
        "zenuml",
    }
)

_VALLA_APERTURA = re.compile(r"^ {0,3}(?P<valla>`{3,}|~{3,})[ \t]*(?P<info>[^`]*)$")
_PARES = {"[": "]", "{": "}", "(": ")"}
#: Líneas de la traza de Node/Puppeteer que mmdc imprime detrás del error de Mermaid.
_TRAZA = re.compile(r"^\s+at |\((?:https?|file):/|^\s*Parser\.parseError")


@dataclasses.dataclass(frozen=True)
class Bloque:
    """Un bloque ```` ```mermaid ```` encontrado en un Markdown.

    Attributes:
        fichero: Ruta del Markdown que lo contiene.
        linea: Número de línea (desde 1) de la valla de apertura.
        texto: Contenido del bloque, sin las vallas.
    """

    fichero: pathlib.Path
    linea: int
    texto: str

    @property
    def etiqueta(self) -> str:
        """Devuelve ``fichero:línea`` para los mensajes."""
        return f"{self.fichero.as_posix()}:{self.linea}"


@dataclasses.dataclass(frozen=True)
class Resultado:
    """Resultado de comprobar un bloque.

    Attributes:
        bloque: El bloque comprobado.
        ok: ``True`` si el diagrama es válido.
        detalle: Tipo de diagrama si es válido, o el motivo del fallo.
    """

    bloque: Bloque
    ok: bool
    detalle: str


def extraer_bloques(texto: str, fichero: pathlib.Path) -> list[Bloque]:
    """Extrae los bloques ```` ```mermaid ```` de un Markdown.

    Respeta las vallas anidadas: un ```` ```mermaid ```` escrito dentro de un bloque
    ````` ````md ````` de ejemplo no cuenta como diagrama.

    Args:
        texto: Contenido completo del Markdown.
        fichero: Ruta del fichero, solo para etiquetar los bloques.

    Returns:
        Los bloques en el orden en que aparecen.
    """
    bloques: list[Bloque] = []
    valla_abierta: str | None = None
    es_mermaid = False
    inicio = 0
    cuerpo: list[str] = []
    for numero, linea in enumerate(texto.splitlines(), start=1):
        if valla_abierta is None:
            coincidencia = _VALLA_APERTURA.match(linea)
            if coincidencia is None:
                continue
            valla_abierta = coincidencia.group("valla")
            info = coincidencia.group("info").strip().lower()
            es_mermaid = info == "mermaid" or info.startswith("mermaid ")
            inicio = numero
            cuerpo = []
            continue
        sin_sangria = linea.lstrip(" ")
        cierra = (
            len(linea) - len(sin_sangria) <= 3
            and sin_sangria.startswith(valla_abierta)
            and not sin_sangria.rstrip().strip(valla_abierta[0])
        )
        if cierra:
            if es_mermaid:
                bloques.append(Bloque(fichero, inicio, "\n".join(cuerpo)))
            valla_abierta = None
            continue
        cuerpo.append(linea)
    return bloques


def lineas_significativas(texto: str) -> list[str]:
    """Quita el front matter, las directivas ``%%{...}%%`` y los comentarios ``%%``.

    Args:
        texto: Contenido de un diagrama.

    Returns:
        Las líneas que quedan, sin espacios a los lados y sin líneas vacías.
    """
    lineas = [linea.strip() for linea in texto.splitlines()]
    if lineas and lineas[0] == "---":
        try:
            fin = lineas.index("---", 1)
        except ValueError:
            fin = len(lineas) - 1
        lineas = lineas[fin + 1 :]
    return [linea for linea in lineas if linea and not linea.startswith("%%")]


def tipo_de_diagrama(texto: str) -> str | None:
    """Devuelve el tipo de diagrama (primer token) o ``None`` si no se reconoce.

    Args:
        texto: Contenido de un diagrama.

    Returns:
        El primer token tal como está escrito (p. ej. ``flowchart`` o
        ``stateDiagram-v2``), o ``None`` si está vacío o no es un tipo conocido.
    """
    lineas = lineas_significativas(texto)
    if not lineas:
        return None
    token = lineas[0].split()[0].rstrip(":")
    base = re.sub(r"-(beta|v\d+)$", "", token)
    return token if base in TIPOS_CONOCIDOS else None


def desequilibrio(texto: str) -> str | None:
    """Busca corchetes, llaves o paréntesis sin cerrar fuera de comillas.

    Solo tiene sentido en diagramas de flujo: en un ``erDiagram`` las llaves forman
    parte de las cardinalidades (``||--o{``) y no van por parejas.

    Args:
        texto: Contenido de un diagrama de flujo.

    Returns:
        Una descripción del primer desequilibrio, o ``None`` si todo cuadra.
    """
    pila: list[tuple[str, int]] = []
    for numero, linea in enumerate(texto.splitlines(), start=1):
        if linea.strip().startswith("%%"):
            continue
        entre_comillas = False
        for caracter in linea:
            if caracter == '"':
                entre_comillas = not entre_comillas
            elif entre_comillas:
                continue
            elif caracter in _PARES:
                pila.append((caracter, numero))
            elif caracter in _PARES.values():
                if not pila or _PARES[pila[-1][0]] != caracter:
                    return f"«{caracter}» sin abrir en la línea {numero} del diagrama"
                pila.pop()
        if entre_comillas:
            return f"comillas sin cerrar en la línea {numero} del diagrama"
    if pila:
        caracter, numero = pila[-1]
        return f"«{caracter}» sin cerrar desde la línea {numero} del diagrama"
    return None


def comprobar_minimo(bloque: Bloque) -> Resultado:
    """Aplica el chequeo mínimo (sin mmdc) a un bloque.

    Args:
        bloque: El bloque a comprobar.

    Returns:
        El resultado, con el tipo de diagrama si es válido.
    """
    tipo = tipo_de_diagrama(bloque.texto)
    if tipo is None:
        primera = next(iter(lineas_significativas(bloque.texto)), "")
        motivo = "bloque vacío" if not primera else f"tipo de diagrama desconocido: «{primera}»"
        return Resultado(bloque, False, motivo)
    if tipo in {"flowchart", "graph"}:
        problema = desequilibrio(bloque.texto)
        if problema is not None:
            return Resultado(bloque, False, problema)
    return Resultado(bloque, True, tipo)


def localizar_mmdc(usar_npx: bool) -> list[str] | None:
    """Decide con qué orden se invoca mermaid-cli.

    Args:
        usar_npx: Si es ``True``, se usa ``npx -y @mermaid-js/mermaid-cli@VERSION``
            aunque haya un ``mmdc`` instalado.

    Returns:
        La orden (lista de argumentos) o ``None`` si no hay forma de ejecutar mmdc.
    """
    if usar_npx:
        npx = shutil.which("npx")
        return [npx, "-y", f"@mermaid-js/mermaid-cli@{VERSION_MMDC}"] if npx else None
    mmdc = shutil.which("mmdc")
    return [mmdc] if mmdc else None


def renderizar(bloque: Bloque, orden: Sequence[str], directorio: pathlib.Path) -> Resultado:
    """Renderiza un bloque a SVG con mermaid-cli.

    Args:
        bloque: El bloque a renderizar.
        orden: Orden base de mermaid-cli (ya con ``--puppeteerConfigFile`` si hace falta).
        directorio: Directorio temporal donde escribir la entrada y la salida.

    Returns:
        El resultado; si mmdc falla, ``detalle`` lleva las últimas líneas de su salida.
    """
    nombre = f"{bloque.fichero.stem}-{bloque.linea}"
    entrada = directorio / f"{nombre}.mmd"
    salida = directorio / f"{nombre}.svg"
    entrada.write_text(bloque.texto + "\n", encoding="utf-8")
    try:
        proceso = subprocess.run(
            [*orden, "--quiet", "--input", str(entrada), "--output", str(salida)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Resultado(bloque, False, "mmdc no terminó en 180 s")
    if proceso.returncode == 0 and salida.exists():
        return Resultado(bloque, True, tipo_de_diagrama(bloque.texto) or "diagrama")
    # mmdc imprime el error de Mermaid («Parse error on line 2: … Expecting …») seguido de la
    # traza de Puppeteer; se conserva lo primero y se descarta la traza.
    mensaje = [
        linea.strip()
        for linea in f"{proceso.stderr}\n{proceso.stdout}".splitlines()
        if linea.strip() and not _TRAZA.search(linea)
    ]
    resumen = " | ".join(mensaje[:5])
    return Resultado(bloque, False, resumen or f"mmdc terminó con código {proceso.returncode}")


def resolver_ficheros(patrones: Iterable[str]) -> list[pathlib.Path]:
    """Expande patrones (``docs/*.md``) y comprueba que los ficheros sueltos existen.

    Args:
        patrones: Rutas o patrones glob.

    Returns:
        Las rutas, sin duplicados y en el orden dado.

    Raises:
        FileNotFoundError: Si una ruta sin comodines no existe.
    """
    ficheros: list[pathlib.Path] = []
    for patron in patrones:
        if any(caracter in patron for caracter in "*?["):
            coincidencias = sorted(pathlib.Path(ruta) for ruta in glob.glob(patron))
        else:
            ruta = pathlib.Path(patron)
            if not ruta.is_file():
                raise FileNotFoundError(patron)
            coincidencias = [ruta]
        for ruta in coincidencias:
            if ruta not in ficheros:
                ficheros.append(ruta)
    return ficheros


def comprobar(ficheros: Sequence[pathlib.Path], orden: Sequence[str] | None) -> list[Resultado]:
    """Comprueba todos los bloques de los ficheros dados.

    Args:
        ficheros: Markdown a revisar.
        orden: Orden de mermaid-cli, o ``None`` para quedarse en el chequeo mínimo.

    Returns:
        Un resultado por bloque, en orden de aparición.
    """
    bloques = [
        bloque for fichero in ficheros for bloque in extraer_bloques(fichero.read_text(encoding="utf-8"), fichero)
    ]
    resultados = [comprobar_minimo(bloque) for bloque in bloques]
    if orden is None:
        return resultados
    with tempfile.TemporaryDirectory(prefix="mermaid-") as temporal:
        directorio = pathlib.Path(temporal)
        return [
            renderizar(resultado.bloque, orden, directorio) if resultado.ok else resultado for resultado in resultados
        ]


def _argumentos(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="comprobar_mermaid",
        description="Comprueba los diagramas Mermaid de los Markdown del kit.",
    )
    parser.add_argument(
        "ficheros",
        nargs="*",
        help=f"Markdown o patrones glob (por defecto: {' '.join(FICHEROS_POR_DEFECTO)})",
    )
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument(
        "--npx",
        action="store_true",
        help=f"ejecuta mermaid-cli {VERSION_MMDC} con «npx -y» aunque no haya mmdc instalado",
    )
    modo.add_argument(
        "--sin-mmdc",
        action="store_true",
        help="no renderiza: solo el chequeo mínimo de sintaxis",
    )
    parser.add_argument(
        "--sin-sandbox",
        action="store_true",
        help="lanza Chromium con --no-sandbox (necesario en runners de CI y contenedores)",
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
    for flujo in (sys.stdout, sys.stderr):
        # Que una consola Windows sin UTF-8 no tumbe el script por una «ñ» en un mensaje.
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(errors="replace")
    try:
        ficheros = resolver_ficheros(args.ficheros or FICHEROS_POR_DEFECTO)
    except FileNotFoundError as error:
        print(f"ERROR: no existe el fichero {error}", file=sys.stderr)
        return 2
    if not ficheros:
        print("ERROR: ningún fichero coincide con los patrones dados", file=sys.stderr)
        return 2

    orden = None if args.sin_mmdc else localizar_mmdc(args.npx)
    modo = "chequeo mínimo (sin mmdc)"
    with tempfile.TemporaryDirectory(prefix="puppeteer-") as temporal:
        if orden is not None:
            modo = f"renderizado con {pathlib.Path(orden[0]).name} {' '.join(orden[1:])}".strip()
            if args.sin_sandbox:
                configuracion = pathlib.Path(temporal) / "puppeteer.json"
                configuracion.write_text(
                    json.dumps({"args": ["--no-sandbox", "--disable-setuid-sandbox"]}),
                    encoding="utf-8",
                )
                orden = [*orden, "--puppeteerConfigFile", str(configuracion)]
        elif not args.sin_mmdc:
            print("AVISO: mmdc no está en el PATH; solo el chequeo mínimo", file=sys.stderr)
        resultados = comprobar(ficheros, orden)

    for resultado in resultados:
        estado = "OK   " if resultado.ok else "FALLO"
        print(f"{estado} {resultado.bloque.etiqueta} ({resultado.detalle})")
    fallos = sum(1 for resultado in resultados if not resultado.ok)
    print(
        f"{len(resultados)} diagramas en {len(ficheros)} ficheros, {modo}: "
        + ("todos válidos" if fallos == 0 else f"{fallos} con errores")
    )
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
