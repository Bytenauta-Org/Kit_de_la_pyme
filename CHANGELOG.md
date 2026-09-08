# Registro de cambios

*In English: this log is kept in Spanish. What changed in the kit itself is summarised in [`README.en.md`](README.en.md); the versioning policy is in [`docs/en/metodologia.md`](docs/en/metodologia.md#data-versioning).*

Todos los cambios relevantes de este repositorio se anotan aquí. El formato sigue [Keep a Changelog 1.1.0](https://keepachangelog.com/es-ES/1.1.0/) y el versionado es [semántico](https://semver.org/lang/es/). La versión del kit de datos y la del código van juntas: cualquier cambio en un fichero de `datos/`, en un prompt, en un esquema o en una regla de puntuación es una versión mayor; ficheros o tareas nuevas, una menor; documentación y código sin efecto en las cifras, un parche. Detalles en [`docs/metodologia.md`](docs/metodologia.md#versionado-de-los-datos).

## [Sin publicar]

### Cambiado

- Documentación bilingüe. `README.md` y los cinco documentos de `docs/` tienen ahora un hermano completo en inglés (`README.en.md` y `docs/en/<nombre>.md`, con el mismo nombre de fichero) y un selector de idioma en la primera línea de los dos. La sección «In English» del README, que era un párrafo al final, desaparece. Índice bilingüe nuevo en `docs/README.md`. La prosa se escribe en su idioma; los ids de tarea, los subcomandos, las opciones, las claves del JSON, los prompts y las frases de fallo siguen en español en las dos versiones porque son el objeto medido. Las reglas están en `CONTRIBUTING.md`, y `tests/test_documentacion.py` comprueba que cada par existe, que empiezan por su selector y que tienen las mismas secciones.
- `README.md` reescrito alrededor de lo que el programa imprime de verdad: salidas literales de `tareas`, `puntuar` y `verificar`, la tabla completa de los seis subcomandos y sus opciones, y la estructura del repositorio con `tools/`.
- `docs/reproducir.md` incorpora una referencia de la CLI con todas las opciones de cada subcomando y los códigos de salida (0, 1 y 3), documenta que `--endpoint` es opcional cuando el id del modelo lleva prefijo de proveedor conocido, y añade `--casos N` para probar una muestra antes de pagar la tarea entera.
- `docs/tareas.md`, `docs/datos.md` y `docs/puntuacion.md` incluyen la salida literal de `tareas`, `casos`, `prompt`, `puntuar` y `verificar` (también la de `verificar` cuando los datos no son los publicados).
- `CONTRIBUTING.md` sustituye el bucle manual de `npx @mermaid-js/mermaid-cli` por `python tools/comprobar_mermaid.py --npx`, que es lo que corre la CI y lo que pide la plantilla de pull request.
- La integración continua alcanza ya la documentación inglesa: el trabajo `mermaid` renderiza los 30 diagramas de los dos README y de `docs/` en los dos idiomas (antes veía 15), el trabajo `datos` incluye `README.en.md` en el control de UTF-8 sin BOM, y `tools/comprobar_mermaid.py` sin argumentos comprueba lo mismo que la CI.
- `tests/test_documentacion.py`, nuevo: cada documento español tiene su hermano inglés y al revés, los doce empiezan por su selector exacto, cada par tiene el mismo número de encabezados `##` y `###`, y `docs/README.md` los lista.

### Corregido

- `python -m kit_pyme prompt <tarea>` no terminaba la salida en un salto de línea en tres de las cinco tareas: el código decidía mirando `tarea.prompt` y escribía `tarea.system`, que lleva pegada la línea `FORMATO`. Ahora mide el texto que de verdad escribe.
- `prompt` y `casos` redirigidos a un fichero en Windows salían con saltos de línea CRLF, y entonces el SHA-256 del volcado dejaba de ser el publicado. `stdout` y `stderr` se reconfiguran también con `newline="\n"`, no solo con la codificación.
- `python -m kit_pyme puntuar` rechazaba un `respuestas.jsonl` con marca de orden de bytes, que es lo que dejan el Bloc de notas y `Out-File -Encoding utf8` de PowerShell 5.1. `leer_jsonl` lee en `utf-8-sig`, que lee igual un fichero sin marca.

Ninguno de los tres toca una regla de puntuación, un prompt ni un byte de `datos/`, así que ninguna cifra publicada cambia.

### Propuesto al blog

- Añadir en la tabla de precios del pipeline del blog alias para los nombres de modelo con fecha que devuelve la API (`claude-haiku-4-5-20251001` y similares). Hoy caen en la tarifa `por_defecto` y el coste publicado sale más alto que el real; el kit copia ese comportamiento a propósito para calcular lo mismo que el blog. Cuando cambie allí, cambiará aquí en la misma versión.

## [1.0.0] - 2026-09-08

Primera versión pública. Sustituye al zip `kit-de-la-pyme.zip` que enlazaba el blog.

### Añadido

- `datos/`: los 85 ficheros del kit del pipeline del blog (20 pedidos con tarifa y clientes, 30 correos, el contrato con sus 15 preguntas, 25 facturas con el registro previo, la hoja de cobros), byte a byte los que se usaron para las cifras de la semana 2026-W37. UTF-8 sin BOM, LF.
- `datos/esquemas/`: JSON Schema de cada fichero de verdad y de la respuesta de cada tarea.
- `datos/CHECKSUMS.sha256`: una línea por fichero de datos, en el formato de `sha256sum`.
- `tareas/<id>/tarea.json`: las cinco tareas con su prompt de sistema literal (con marcadores donde el blog interpola un fichero), su esquema, `max_tokens`, el fichero de verdad y cómo se construye la entrada de cada caso.
- `kit_pyme/`: paquete Python 3.11+ sin dependencias externas con la CLI `tareas`, `casos`, `prompt`, `puntuar`, `ejecutar` y `verificar`, la puntuación regla por regla del blog (incluidos los redondeos de JavaScript) y `precios.json`.
- `tests/`: paridad con las salidas reales del código del blog (prompts por SHA-256, respuestas verdaderas al 100 %, respuestas trucadas por regla, normalización, veredictos, notas, redondeos), CLI y servidor falso local.
- `resultados/2026-W37.json`: las cifras publicadas en el primer número del blog (Haiku 4.5: pedidos 15/20, 16,9 s, 0,3822 €; facturas 24/25, 10,5 s, 0,1428 €) con su procedencia.
- Documentación: `README.md` con diagramas Mermaid, `docs/tareas.md`, `docs/datos.md`, `docs/puntuacion.md`, `docs/reproducir.md`, `docs/metodologia.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), `SECURITY.md`, `CITATION.cff`. Solo en español; la versión inglesa llega en la siguiente versión.
- CI: `ruff` (lint y formato), `pytest`, `python -m kit_pyme verificar` y validación de los diagramas Mermaid. Plantillas de issue (dato incorrecto, resultado con tu herramienta, tarea nueva) y de pull request. `pyproject.toml`, `.editorconfig`, `.gitattributes`.
- Licencia CC BY 4.0 para todo el repositorio (`LICENSE`).

### Conocido

Se documenta y no se corrige en 1.x, porque las cifras publicadas se midieron así:

- El prompt de `redactar-recordatorio` pide «menos de 200 palabras» y la regla admite hasta 220 (`max_palabras`). Manda la regla.
- Un nombre de modelo con fecha devuelto por la API no está en la tabla de precios y se tarifa como `por_defecto` (ver «Propuesto al blog»).
- El recorte a 80 caracteres de la respuesta en la frase de fallo del contrato cuenta unidades UTF-16 en el blog y puntos de código en el kit; solo difiere si hay emoji u otros caracteres fuera del plano básico en esos 80.
- Las cifras de 2026-W37 se midieron desde un Worker de Cloudflare; los segundos medidos desde otra máquina no son directamente comparables.

[Sin publicar]: https://github.com/Bytenauta-Org/Kit_de_la_pyme/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Bytenauta-Org/Kit_de_la_pyme/releases/tag/v1.0.0
