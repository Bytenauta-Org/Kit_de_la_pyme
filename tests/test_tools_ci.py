"""Pruebas de los scripts de ``tools/`` que usa la integración continua.

Los scripts no forman parte del paquete ``kit_pyme`` (no se instalan), así que se cargan
por ruta. Las pruebas que necesitan ``mmdc`` se saltan si no está en el ``PATH``.
"""

from __future__ import annotations

import importlib.util
import pathlib
import shutil
import sys
import types

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def _cargar(nombre: str) -> types.ModuleType:
    ruta = RAIZ / "tools" / f"{nombre}.py"
    especificacion = importlib.util.spec_from_file_location(f"tools.{nombre}", ruta)
    assert especificacion is not None and especificacion.loader is not None
    modulo = importlib.util.module_from_spec(especificacion)
    # Los dataclass con «from __future__ import annotations» buscan el módulo en sys.modules.
    sys.modules[especificacion.name] = modulo
    especificacion.loader.exec_module(modulo)
    return modulo


mermaid = _cargar("comprobar_mermaid")
changelog = _cargar("version_changelog")

MARKDOWN = """\
# Título

```mermaid
flowchart LR
    A[Kit] --> B{Puntuar}
    B -->|"ok (sí)"| C((Acierto))
```

Texto entre diagramas.

````md
Un ejemplo de cómo se escribe un diagrama, que NO es un diagrama:

```mermaid
esto no es un diagrama
```
````

~~~mermaid
erDiagram
    CLIENTE ||--o{ PEDIDO : hace
~~~

```python
print("no es mermaid")
```
"""

CHANGELOG = """\
# Changelog

Todas las novedades del kit de datos.

## [Sin publicar]

- Algo pendiente.

## [1.1.0] - 2026-10-05

### Changed

- Corregido el IVA de factura-11.

### Added

- Esquema JSON de cobros-verdad.

## [1.0.0] - 2026-09-08

### Added

- Los datos de hoy.

[Sin publicar]: https://github.com/Bytenauta-Org/Kit_de_la_pyme/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/Bytenauta-Org/Kit_de_la_pyme/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Bytenauta-Org/Kit_de_la_pyme/releases/tag/v1.0.0
"""


# --- comprobar_mermaid ----------------------------------------------------------------


def test_extraer_bloques_respeta_vallas_anidadas_y_tildes() -> None:
    """Saca los dos diagramas reales, ignora el ejemplo dentro de ````md y el bloque python."""
    bloques = mermaid.extraer_bloques(MARKDOWN, pathlib.Path("x.md"))
    assert [(b.linea, b.texto.split()[0]) for b in bloques] == [(3, "flowchart"), (19, "erDiagram")]
    assert bloques[0].etiqueta == "x.md:3"


@pytest.mark.parametrize(
    ("texto", "tipo"),
    [
        ("flowchart TD\n  A --> B", "flowchart"),
        ("graph LR\n  A --> B", "graph"),
        ("%%{init: {'theme': 'neutral'}}%%\nsequenceDiagram\n  A->>B: hola", "sequenceDiagram"),
        ("---\ntitle: Con front matter\n---\nstateDiagram-v2\n  [*] --> A", "stateDiagram-v2"),
        ("erDiagram\n  A ||--o{ B : tiene", "erDiagram"),
        ("xychart-beta\n  x-axis [a, b]\n  bar [1, 2]", "xychart-beta"),
        ("gitGraph LR:\n  commit", "gitGraph"),
    ],
)
def test_tipo_de_diagrama_reconoce_los_tipos_habituales(texto: str, tipo: str) -> None:
    """El primer token, sin front matter ni directivas, identifica el diagrama."""
    assert mermaid.tipo_de_diagrama(texto) == tipo


@pytest.mark.parametrize(
    ("texto", "fragmento"),
    [
        ("", "bloque vacío"),
        ("%% solo un comentario", "bloque vacío"),
        ("diagramaInventado\n  A --> B", "tipo de diagrama desconocido"),
        ("flowchart LR\n  A[Texto --> B", "«[» sin cerrar"),
        ("flowchart LR\n  A --> B]", "«]» sin abrir"),
        ('flowchart LR\n  A["sin cerrar] --> B', "comillas sin cerrar"),
    ],
)
def test_chequeo_minimo_detecta_los_errores_evidentes(texto: str, fragmento: str) -> None:
    """Sin mmdc, el chequeo mínimo atrapa bloques vacíos, tipos raros y corchetes sueltos."""
    resultado = mermaid.comprobar_minimo(mermaid.Bloque(pathlib.Path("x.md"), 1, texto))
    assert not resultado.ok
    assert fragmento in resultado.detalle


def test_chequeo_minimo_no_se_confunde_con_las_llaves_de_un_er() -> None:
    """En un erDiagram las llaves son cardinalidades, no parejas: no se comprueban."""
    bloque = mermaid.Bloque(pathlib.Path("x.md"), 1, "erDiagram\n  A ||--o{ B : tiene")
    assert mermaid.comprobar_minimo(bloque).ok


def test_main_sin_mmdc_devuelve_0_1_o_2(tmp_path: pathlib.Path) -> None:
    """0 si todo es válido, 1 si un diagrama falla, 2 si el fichero no existe."""
    bueno = tmp_path / "bueno.md"
    bueno.write_text(MARKDOWN, encoding="utf-8")
    malo = tmp_path / "malo.md"
    malo.write_text("```mermaid\nflowchart LR\n  A[Sin cerrar --> B\n```\n", encoding="utf-8")
    assert mermaid.main(["--sin-mmdc", str(bueno)]) == 0
    assert mermaid.main(["--sin-mmdc", str(bueno), str(malo)]) == 1
    assert mermaid.main(["--sin-mmdc", str(tmp_path / "no-existe.md")]) == 2


@pytest.mark.skipif(shutil.which("mmdc") is None, reason="mermaid-cli (mmdc) no está en el PATH")
def test_mmdc_renderiza_los_validos_y_rechaza_los_rotos(tmp_path: pathlib.Path) -> None:
    """Con mmdc de verdad: un diagrama sintácticamente correcto pasa y uno roto no."""
    fichero = tmp_path / "ambos.md"
    bueno = "```mermaid\nflowchart LR\n  A --> B\n```\n"
    roto = "```mermaid\nflowchart LR\n  A -> B --> \n```\n"
    fichero.write_text(bueno + "\n" + roto, encoding="utf-8")
    resultados = mermaid.comprobar([fichero], mermaid.localizar_mmdc(usar_npx=False))
    assert [r.ok for r in resultados] == [True, False]


def test_los_markdown_del_repositorio_pasan_el_chequeo_minimo() -> None:
    """Todo diagrama del README y de docs/ tiene un tipo conocido y los corchetes cuadran."""
    ficheros = [RAIZ / "README.md", *sorted((RAIZ / "docs").glob("*.md"))]
    ficheros = [f for f in ficheros if f.is_file()]
    if not ficheros:
        pytest.skip("todavía no hay README.md ni docs/ en esta copia")
    fallos = [r for r in mermaid.comprobar(ficheros, None) if not r.ok]
    assert fallos == [], [f"{r.bloque.etiqueta}: {r.detalle}" for r in fallos]


# --- version_changelog ----------------------------------------------------------------


def test_version_vigente_ignora_sin_publicar_y_las_referencias() -> None:
    """La vigente es la primera sección numerada; las notas no llevan los enlaces del pie."""
    vigente = changelog.version_vigente(CHANGELOG)
    assert (vigente.numero, vigente.fecha) == ("1.1.0", "2026-10-05")
    assert vigente.notas.startswith("### Changed")
    assert "factura-11" in vigente.notas
    assert "https://" not in vigente.notas
    assert [v.numero for v in changelog.leer_versiones(CHANGELOG)] == ["1.1.0", "1.0.0"]


@pytest.mark.parametrize(
    "encabezado",
    ["## [1.0.0] - 2026-09-08", "## 1.0.0 (2026-09-08)", "## v1.0.0", "## [v1.0.0] — 2026-09-08"],
)
def test_se_admiten_varias_formas_de_encabezado(encabezado: str) -> None:
    """Keep a Changelog con corchetes, con paréntesis, con «v» o con raya."""
    assert changelog.version_vigente(f"# Changelog\n\n{encabezado}\n\n- Algo.\n").numero == "1.0.0"


def test_sin_version_lanza_valueerror() -> None:
    """Un CHANGELOG solo con «Sin publicar» no tiene versión vigente."""
    with pytest.raises(ValueError, match="ninguna sección"):
        changelog.version_vigente("# Changelog\n\n## [Sin publicar]\n\n- Nada.\n")


def test_main_github_output_notas_y_comprobar(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    """La CLI vuelca version/fecha, escribe las notas y falla si la versión no cuadra."""
    fichero = tmp_path / "CHANGELOG.md"
    fichero.write_text(CHANGELOG, encoding="utf-8")
    notas = tmp_path / "notas.md"
    assert changelog.main([str(fichero), "--github-output", "--notas", str(notas)]) == 0
    assert capsys.readouterr().out.splitlines() == ["version=1.1.0", "fecha=2026-10-05"]
    assert notas.read_text(encoding="utf-8").startswith("### Changed")
    assert changelog.main([str(fichero), "--comprobar", "v1.1.0"]) == 0
    assert changelog.main([str(fichero), "--comprobar", "1.0.0"]) == 1
    assert changelog.main([str(tmp_path / "no.md")]) == 2


def test_el_changelog_del_repositorio_tiene_version_vigente() -> None:
    """El CHANGELOG real (si existe en esta copia) empieza por una versión X.Y.Z con fecha."""
    ruta = RAIZ / "CHANGELOG.md"
    if not ruta.is_file():
        pytest.skip("todavía no hay CHANGELOG.md en esta copia")
    vigente = changelog.version_vigente(ruta.read_text(encoding="utf-8"))
    assert vigente.fecha is not None, "la versión vigente debe llevar fecha AAAA-MM-DD"
