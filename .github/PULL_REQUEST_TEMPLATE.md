<!--
Gracias por la PR. El título sigue Conventional Commits en inglés
(feat, fix, docs, data, test, ci, build, chore, refactor), por ejemplo:
  data: fix VAT on factura-11 (v1.0.1)
  docs: add ER diagram to datos.md
  feat(cli): add --casos to ejecutar
-->

## Qué cambia

<!-- Una o dos frases: qué había, qué hay ahora y por qué. Enlaza el issue si lo hay (Closes #12). -->

## Tipo de cambio

- [ ] Datos (`datos/`): cambia algún fichero de datos, un `*-verdad.json` o un esquema
- [ ] Tarea (`tareas/`): prompt, esquema de respuesta o forma de construir los casos
- [ ] Código (`kit_pyme/`, `tools/`): CLI, puntuación, ejecución contra un endpoint
- [ ] Documentación (`README.md`, `docs/`)
- [ ] Resultado publicado (`resultados/`)
- [ ] Infraestructura (`.github/`, `pyproject.toml`, tests)

## Comprobaciones

- [ ] `ruff check .` y `ruff format --check .` pasan
- [ ] `pytest -q` pasa
- [ ] `python -m kit_pyme verificar` pasa
- [ ] `python tools/comprobar_mermaid.py` pasa (si tocas Markdown con diagramas)

### Solo si tocas datos o tareas

La puntuación del kit tiene que seguir siendo **idéntica** a la del blog, regla por regla, o las cifras dejan de ser comparables.

- [ ] He subido la versión del kit (semver) y la he anotado en `CHANGELOG.md` con qué cambia y por qué
- [ ] He regenerado `datos/CHECKSUMS.sha256` y `python -m kit_pyme verificar` pasa
- [ ] He actualizado los JSON Schema de `datos/esquemas/` si cambia la forma de algún fichero
- [ ] No he cambiado ni una coma del prompt ni del esquema de ninguna tarea sin decirlo aquí y sin coordinarlo con el pipeline del blog
- [ ] Las respuestas verdaderas siguen puntuando el 100 % (`pytest -q` lo comprueba)

### Solo si añades un resultado

- [ ] El fichero de `resultados/` tiene la forma `ResultadoPrueba` (tarea, tarea_nombre, casos, aciertos, fallos, segundos, coste_eur, veredicto, nota, modelo)
- [ ] Indica la versión del kit y cómo se ejecutó (temperatura, concurrencia, desde dónde se midieron los segundos)

## Licencia

- [ ] Acepto que esta contribución se publique bajo CC BY 4.0, como el resto del repositorio
