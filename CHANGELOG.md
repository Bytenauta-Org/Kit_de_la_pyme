# Registro de cambios

Todos los cambios relevantes de este repositorio se anotan aquí. El formato sigue [Keep a Changelog 1.1.0](https://keepachangelog.com/es-ES/1.1.0/) y el versionado es [semántico](https://semver.org/lang/es/). La versión del kit de datos y la del código van juntas: cualquier cambio en un fichero de `datos/`, en un prompt, en un esquema o en una regla de puntuación es una versión mayor; ficheros o tareas nuevas, una menor; documentación y código sin efecto en las cifras, un parche. Detalles en [`docs/metodologia.md`](docs/metodologia.md#versionado-de-los-datos).

## [Sin publicar]

### Propuesto al blog

- Añadir en la tabla de precios del pipeline del blog alias para los nombres de modelo con fecha que devuelve la API (`claude-haiku-4-5-20251001` y similares). Hoy caen en la tarifa `por_defecto` y el coste publicado sale más alto que el real; el kit copia ese comportamiento a propósito para calcular lo mismo que el blog. Cuando cambie allí, cambiará aquí en la misma versión.

## [1.0.0] - 2026-09-08

Primera versión pública. Sustituye al zip `kit-de-la-pyme.zip` que enlazaba el blog.

### Añadido

- `datos/`: los 85 ficheros del kit del pipeline del blog (20 pedidos con tarifa y clientes, 30 correos, el contrato con sus 15 preguntas, 25 facturas con el registro previo, la hoja de cobros), byte a byte los que se usaron para las cifras de la semana 2026-W37. UTF-8 sin BOM, LF.
- `datos/esquemas/`: JSON Schema de cada fichero de verdad y de la respuesta de cada tarea.
- `datos/CHECKSUMS.sha256`: una línea por fichero de datos, en el formato de `sha256sum`.
- `tareas/<id>/tarea.json`: las cinco tareas con su prompt de sistema literal (con marcadores donde el blog interpola un fichero), su esquema, `max_tokens`, el fichero de verdad y cómo se construye la entrada de cada caso.
- `kit_pyme/`: paquete Python 3.11+ sin dependencias externas con la CLI `tareas`, `casos`, `puntuar`, `ejecutar` y `verificar`, la puntuación regla por regla del blog (incluidos los redondeos de JavaScript) y `precios.json`.
- `tests/`: paridad con las salidas reales del código del blog (prompts por SHA-256, respuestas verdaderas al 100 %, respuestas trucadas por regla, normalización, veredictos, notas, redondeos), CLI y servidor falso local.
- `resultados/2026-W37.json`: las cifras publicadas en el primer número del blog (Haiku 4.5: pedidos 15/20, 16,9 s, 0,3822 €; facturas 24/25, 10,5 s, 0,1428 €) con su procedencia.
- Documentación: `README.md` con diagramas Mermaid, `docs/tareas.md`, `docs/datos.md`, `docs/puntuacion.md`, `docs/reproducir.md`, `docs/metodologia.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), `SECURITY.md`, `CITATION.cff`.
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
