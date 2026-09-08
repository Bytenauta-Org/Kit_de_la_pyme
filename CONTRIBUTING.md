# Contribuir al kit de la pyme

Gracias por dedicarle tiempo. Este documento dice qué contribuciones se aceptan, cómo se preparan y qué comprueba la integración continua antes de fusionar nada.

Índice: [Qué se acepta](#qué-se-acepta) · [Flujo de trabajo](#flujo-de-trabajo) · [Conventional Commits](#conventional-commits) · [Estilo del código](#estilo-del-código) · [Tests](#tests) · [Cambios en los datos](#cambios-en-los-datos) · [Cambios en prompts, esquemas y reglas](#cambios-en-prompts-esquemas-y-reglas) · [Documentación y diagramas](#documentación-y-diagramas) · [Comprobaciones locales](#comprobaciones-locales) · [Licencia de las contribuciones](#licencia-de-las-contribuciones)

## Qué se acepta

Tres tipos de contribución, cada uno con su plantilla de issue en `.github/`:

| Tipo | Plantilla | Qué hace falta |
|---|---|---|
| **Dato incorrecto** | «Dato incorrecto» | El fichero, el caso, qué dice, qué debería decir y por qué (una norma, un cálculo, una fuente). Se discute en el issue; si se confirma, se anota en `CHANGELOG.md` y se corrige en la siguiente versión mayor |
| **Resultado con tu herramienta** | «Resultado con tu herramienta» | El `resultado.json`, la herramienta y el modelo, la fecha, con API o sin ella, la salida de `verificar` y las desviaciones del procedimiento. Ver [`docs/reproducir.md`](docs/reproducir.md) |
| **Tarea nueva** | «Tarea nueva» | Qué tarea de pyme es, qué datos harían falta, qué se puntuaría y con qué regla determinista. Primero se discute el diseño; después el PR |

También se aceptan sin issue previo: correcciones de documentación, mejoras del ejecutor que no cambien la puntuación, tests nuevos y mejoras de la CI.

No se aceptan: cambios que hagan que el kit puntúe distinto que el blog (ver [más abajo](#cambios-en-prompts-esquemas-y-reglas)), dependencias fuera de la biblioteca estándar de Python, datos reales de ninguna empresa o persona, y ficheros binarios en `datos/`.

## Flujo de trabajo

1. Haz un fork y crea una rama desde `main` con un nombre descriptivo: `fix/vencimiento-factura-08`, `docs/reproducir-ollama`, `feat/tarea-albaranes`.
2. Haz commits pequeños con mensajes en formato Conventional Commits, en inglés.
3. Ejecuta las [comprobaciones locales](#comprobaciones-locales).
4. Abre un pull request con la plantilla. Explica qué cambia y por qué, enlaza el issue si lo hay y marca las casillas que apliquen.
5. La CI tiene que estar en verde: `ruff check`, `ruff format --check`, `pytest`, `python -m kit_pyme verificar` y la validación de los diagramas Mermaid.
6. Una persona de Bytenauta revisa y fusiona. Si el cambio afecta a la paridad con el blog, se coordina con el pipeline del blog antes de fusionar.

## Conventional Commits

Los mensajes de commit siguen [Conventional Commits 1.0.0](https://www.conventionalcommits.org/es/v1.0.0/), en inglés, en imperativo y sin punto final en el asunto:

```text
<tipo>[(ámbito)][!]: <resumen en inglés, en minúsculas>

[cuerpo opcional: qué y por qué, no cómo]

[pies opcionales: BREAKING CHANGE: ..., Closes #12]
```

| Tipo | Cuándo |
|---|---|
| `feat` | Funcionalidad nueva en `kit_pyme` (un subcomando, una opción) |
| `fix` | Un error corregido en el código |
| `data` | Cualquier cambio en `datos/` o `tareas/`. Con `!` si cambia un fichero existente, un prompt, un esquema o una regla |
| `docs` | Documentación, README, diagramas, plantillas |
| `test` | Tests nuevos o corregidos, sin tocar el código que prueban |
| `ci` | Workflows de GitHub Actions |
| `build` | `pyproject.toml`, empaquetado |
| `refactor` | Cambio de código sin cambio de comportamiento |
| `chore` | Todo lo demás (`.editorconfig`, `.gitattributes`) |

Ámbitos habituales: `kit_pyme`, `datos`, `tareas`, `docs`, `tests`, `ci`, `resultados`. Ejemplos:

```text
fix(kit_pyme): emulate Math.round for coste_eur instead of Python round
docs(reproducir): add LM Studio endpoint
data(facturas)!: correct due date of factura-08 (v2.0.0)
test: add negative case for duplicate line detection
```

## Estilo del código

El código sigue la [guía de estilo de Google para Python](https://google.github.io/styleguide/pyguide.html) con estas concreciones, todas comprobadas por `ruff` con la configuración de `pyproject.toml`:

- Python 3.11 o superior. Solo biblioteca estándar: las llamadas HTTP se hacen con `urllib`, no con `requests`.
- Línea de 100 caracteres. `ruff format` decide el resto del formato.
- Reglas activas de `ruff`: pycodestyle (`E`, `W`), pyflakes (`F`), isort (`I`) y pydocstyle con la convención `google` (`D`).
- Tipado en todas las firmas públicas. `from __future__ import annotations` donde haga falta.
- Docstrings en estilo Google (secciones `Args:`, `Returns:`, `Raises:`) y escritas en español, como los identificadores, los mensajes de la CLI y los comentarios. La forma es la de Google; el idioma es el del proyecto.
- Nombres de fichero en español y en minúsculas con guiones bajos.
- La CLI habla español y devuelve códigos de salida distintos de cero cuando algo falla; los mensajes de error van a `stderr`.
- Nada de claves ni datos personales en el código, en los tests ni en los ficheros de ejemplo. Las claves entran solo por variable de entorno.

## Tests

`pytest` desde la raíz. Los tests están en `tests/` y se organizan así:

- **Paridad**: por cada tarea, componer el prompt y comprobar su SHA-256; puntuar las respuestas verdaderas y obtener el 100 %; reproducir las salidas grabadas del código del blog (respuestas trucadas con su `ok` y su frase de fallo, funciones de normalización, veredictos y notas, redondeos).
- **Negativos por regla**: por cada regla de cada tarea hay al menos un caso que la hace fallar con la frase exacta.
- **CLI**: `puntuar` sobre un JSONL de ejemplo, `verificar` sobre los checksums (y sobre un fichero alterado), `ejecutar` contra un servidor falso local (`http.server` en `127.0.0.1`) que devuelve respuestas grabadas, incluidos un 400, un 429 y un cuerpo vacío.

Un cambio en una regla de puntuación exige el test que la cubre y la actualización de las salidas grabadas, y es un cambio de versión mayor.

## Cambios en los datos

`datos/` es la parte que nunca cambia en silencio.

- No se edita ningún fichero existente en una versión menor o de parche. Un dato incorrecto confirmado se anota en `CHANGELOG.md` («Conocido») y se corrige en la siguiente versión mayor.
- Añadir ficheros o casos nuevos es una versión menor: entran en el `*-verdad.json` correspondiente, en `datos/esquemas/` si cambia la forma, en `CHECKSUMS.sha256` y en `docs/datos.md`.
- Todo cambio en `datos/` regenera `CHECKSUMS.sha256` en el mismo commit; `python -m kit_pyme verificar` tiene que pasar.
- Los datos son inventados. Un fichero nuevo tiene que cumplir lo mismo que los existentes: NIF con dígito de control válido, dominios `.example`, importes que cuadren, coherencia con `clientes.csv`, `tarifa.csv` y las fechas de referencia. Nada que se parezca a una empresa o persona real.
- UTF-8 sin BOM y saltos de línea LF. `.gitattributes` lo impone; comprueba que tu editor no lo cambie.

## Cambios en prompts, esquemas y reglas

Los prompts de `tareas/`, los esquemas y las reglas de `kit_pyme` son una copia de los del blog «A la última». Cambiarlos aquí sin cambiarlos allí rompe la comparabilidad de todas las cifras publicadas. Por eso:

- Un PR que cambie un prompt, un esquema, un umbral, una frase de fallo o una función de normalización se etiqueta `paridad` y no se fusiona hasta que el pipeline del blog tenga el mismo cambio. Los dos cambios se anotan en `CHANGELOG.md` con la fecha.
- Si crees que una regla puntúa mal (un falso negativo, un formato correcto que no se reconoce), abre un issue de «Dato incorrecto» con el caso y la respuesta. Se decide ahí si cambia la regla (versión mayor) o si el modelo tenía que haber seguido el prompt.
- La incoherencia conocida entre «menos de 200 palabras» (prompt) y `max_palabras: 220` (regla) se mantiene a propósito hasta la siguiente versión mayor.

## Documentación y diagramas

- La documentación está en español, en prosa directa. Frases cortas, sin metáforas, con el dato exacto. El lector es un técnico de pyme o un consultor.
- Los diagramas son Mermaid dentro de bloques ```` ```mermaid ````. La CI los valida con `@mermaid-js/mermaid-cli`; un diagrama que no renderiza bloquea el PR. Usa comillas en las etiquetas con signos de puntuación y evita `;` y `#` en los textos de los diagramas de secuencia.
- Un cambio en la CLI cambia también `README.md` y `docs/reproducir.md` en el mismo PR.
- Los resultados del blog en `resultados/` no se editan; ver [`resultados/README.md`](resultados/README.md).

## Comprobaciones locales

```bash
python -m pip install ruff pytest
ruff check .
ruff format --check .
pytest
python -m kit_pyme verificar
npx -y @mermaid-js/mermaid-cli -i README.md -o /tmp/README.out.md
for f in docs/*.md; do npx -y @mermaid-js/mermaid-cli -i "$f" -o "/tmp/$(basename "$f")"; done
```

La validación de Mermaid necesita Node.js; si no lo tienes, la CI la hará por ti.

## Licencia de las contribuciones

Al contribuir aceptas que tu aportación (datos, documentación o código) se publique bajo la misma licencia que el resto del repositorio, [CC BY 4.0](LICENSE), con atribución a «Kit de la pyme, Bytenauta S.L.» y a los contribuidores que figuran en el historial de Git. No aportes nada que no puedas licenciar así (texto copiado de una fuente con otra licencia, datos de terceros).

Este proyecto se rige por el [código de conducta](CODE_OF_CONDUCT.md). Los problemas de seguridad se comunican como dice [`SECURITY.md`](SECURITY.md).
