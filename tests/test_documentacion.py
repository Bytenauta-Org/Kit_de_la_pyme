"""Comprueba que la documentación española y la inglesa siguen emparejadas.

La portada de los dos README promete que cada documento existe en los dos idiomas, que los
dos empiezan por su selector y que la estructura coincide. Sin estas pruebas la mitad
inglesa se queda atrás en el primer pull request que solo toque el español, y la promesa
pasa a ser falsa sin que nadie se entere.

Lo que se comprueba es la estructura, no la traducción: cada versión se escribe en su
idioma y la inglesa suele salir más corta. Lo que tiene que coincidir es el número de
encabezados ``##`` y ``###`` fuera de los bloques de código.
"""

from __future__ import annotations

import pathlib
import re

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
DOCS = RAIZ / "docs"

# El índice de docs/ es bilingüe en sí mismo (dos columnas), así que no tiene hermano.
SIN_HERMANO = {"README.md"}

SELECTOR_ES = "**Español** · [English]({enlace})"
SELECTOR_EN = "[Español]({enlace}) · **English**"


def documentos_de_docs() -> list[str]:
    """Los nombres de fichero de ``docs/*.md`` que tienen que estar en los dos idiomas."""
    return sorted(p.name for p in DOCS.glob("*.md") if p.name not in SIN_HERMANO)


def pares() -> list[tuple[pathlib.Path, pathlib.Path]]:
    """Cada documento español con su hermano inglés, el README incluido."""
    parejas = [(RAIZ / "README.md", RAIZ / "README.en.md")]
    parejas += [(DOCS / nombre, DOCS / "en" / nombre) for nombre in documentos_de_docs()]
    return parejas


def contar_encabezados(ruta: pathlib.Path) -> tuple[int, int]:
    """Cuenta los encabezados ``##`` y ``###`` de un Markdown, sin mirar dentro del código.

    Args:
        ruta: El fichero Markdown.

    Returns:
        El número de encabezados de nivel 2 y el de nivel 3.
    """
    nivel2 = nivel3 = 0
    en_bloque = False
    for linea in ruta.read_text(encoding="utf-8").split("\n"):
        if linea.startswith("```"):
            en_bloque = not en_bloque
            continue
        if en_bloque:
            continue
        if linea.startswith("### "):
            nivel3 += 1
        elif linea.startswith("## "):
            nivel2 += 1
    return nivel2, nivel3


def id_del_par(par: tuple[pathlib.Path, pathlib.Path]) -> str:
    return par[0].relative_to(RAIZ).as_posix()


def test_hay_al_menos_los_seis_pares_esperados() -> None:
    """El README y los cinco documentos de docs/: si aparece uno nuevo, entra solo."""
    assert len(pares()) >= 6
    assert documentos_de_docs() == [
        "datos.md",
        "metodologia.md",
        "puntuacion.md",
        "reproducir.md",
        "tareas.md",
    ]


@pytest.mark.parametrize("par", pares(), ids=id_del_par)
def test_cada_documento_tiene_hermano_en_el_otro_idioma(
    par: tuple[pathlib.Path, pathlib.Path],
) -> None:
    """``docs/X.md`` va siempre con ``docs/en/X.md``, y README.md con README.en.md."""
    espanol, ingles = par
    assert espanol.is_file(), f"falta {espanol.relative_to(RAIZ)}"
    assert ingles.is_file(), f"falta {ingles.relative_to(RAIZ)}: un documento español sin hermano inglés"


@pytest.mark.parametrize("par", pares(), ids=id_del_par)
def test_los_dos_empiezan_por_su_selector_de_idioma(
    par: tuple[pathlib.Path, pathlib.Path],
) -> None:
    """Primera línea, antes del ``#``: el idioma activo en negrita y el otro como enlace."""
    espanol, ingles = par
    if espanol.parent == RAIZ:
        enlace_es, enlace_en = "README.en.md", "README.md"
    else:
        enlace_es, enlace_en = f"en/{espanol.name}", f"../{espanol.name}"

    primera_es = espanol.read_text(encoding="utf-8").split("\n", 1)[0]
    primera_en = ingles.read_text(encoding="utf-8").split("\n", 1)[0]
    assert primera_es == SELECTOR_ES.format(enlace=enlace_es)
    assert primera_en == SELECTOR_EN.format(enlace=enlace_en)


@pytest.mark.parametrize("par", pares(), ids=id_del_par)
def test_cada_par_tiene_la_misma_estructura(par: tuple[pathlib.Path, pathlib.Path]) -> None:
    """Mismas secciones en los dos idiomas: se traduce la prosa, no se reordena el documento."""
    espanol, ingles = par
    assert contar_encabezados(espanol) == contar_encabezados(ingles), (
        f"{espanol.relative_to(RAIZ)} y {ingles.relative_to(RAIZ)} no tienen las mismas "
        f"secciones: {contar_encabezados(espanol)} contra {contar_encabezados(ingles)}"
    )


def test_el_indice_de_docs_no_lleva_selector_porque_es_bilingue() -> None:
    """``docs/README.md`` no tiene hermano: es una tabla con columna española e inglesa."""
    indice = DOCS / "README.md"
    primera = indice.read_text(encoding="utf-8").split("\n", 1)[0]
    assert not primera.startswith("**Español**")
    assert not primera.startswith("[Español]")
    assert not (DOCS / "en" / "README.md").exists()


def test_el_indice_de_docs_nombra_los_dos_ficheros_de_cada_par() -> None:
    """Si se añade un documento y no se pone en el índice, el índice deja de servir."""
    indice = (DOCS / "README.md").read_text(encoding="utf-8")
    for nombre in documentos_de_docs():
        assert f"({nombre})" in indice, f"{nombre} no está en docs/README.md"
        assert f"(en/{nombre})" in indice, f"en/{nombre} no está en docs/README.md"


def test_no_sobra_ningun_documento_ingles() -> None:
    """Nada en ``docs/en/`` sin su original español: un huérfano no se actualiza nunca."""
    huerfanos = [p.name for p in (DOCS / "en").glob("*.md") if not (DOCS / p.name).is_file()]
    assert huerfanos == []


def fuera_de_bloques(ruta: pathlib.Path) -> str:
    """El texto sin las vallas ```: dentro hay ejemplos de enlaces, no enlaces."""
    lineas, en_bloque = [], False
    for linea in ruta.read_text(encoding="utf-8").split("\n"):
        if linea.lstrip().startswith("```"):
            en_bloque = not en_bloque
            continue
        if not en_bloque:
            lineas.append(linea)
    return "\n".join(lineas)


def markdown_del_repositorio() -> list[pathlib.Path]:
    return sorted(p for p in RAIZ.rglob("*.md") if ".git" not in p.parts)


@pytest.mark.parametrize(
    "documento",
    markdown_del_repositorio(),
    ids=lambda p: p.relative_to(RAIZ).as_posix(),
)
def test_los_enlaces_internos_llevan_a_algun_sitio(documento: pathlib.Path) -> None:
    """Duplicar un documento duplica sus enlaces, y en la copia inglesa apuntan a otro sitio."""
    rotos = [
        destino
        for destino in re.findall(r"\]\(([^)#:]+\.md)(?:#[^)]*)?\)", fuera_de_bloques(documento))
        if not (documento.parent / destino).resolve().is_file()
    ]
    assert rotos == [], f"{documento.relative_to(RAIZ).as_posix()} enlaza a {rotos}"


def test_la_ci_renderiza_todos_los_diagramas() -> None:
    """Un diagrama que la CI no mira se rompe sin que nadie se entere.

    Al hacer bilingüe la documentación se duplicaron los diagramas, y la orden de la CI
    nombraba solo la mitad española: renderizaba 15 de 30.
    """
    ci = (RAIZ / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    orden = next(
        (
            linea
            for linea in ci.split("\n")
            if "tools/comprobar_mermaid.py" in linea and not linea.lstrip().startswith("#") and "hashFiles" not in linea
        ),
        "",
    )
    assert orden, "la CI no ejecuta tools/comprobar_mermaid.py"

    patrones = re.findall(r"[\w./*]+\.md", orden)
    sin_cubrir = [
        documento.relative_to(RAIZ).as_posix()
        for documento in markdown_del_repositorio()
        if "```mermaid" in documento.read_text(encoding="utf-8")
        and not any(
            re.fullmatch(
                patron.replace(".", r"\.").replace("*", "[^/]*"),
                documento.relative_to(RAIZ).as_posix(),
            )
            for patron in patrones
        )
    ]
    assert sin_cubrir == [], f"con diagramas y fuera de la CI: {sin_cubrir}"
