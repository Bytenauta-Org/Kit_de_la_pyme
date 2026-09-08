# Documentación · Documentation

Cada documento existe en español y en inglés, con el mismo nombre de fichero: `docs/<nombre>.md` y `docs/en/<nombre>.md`. Los dos llevan un selector de idioma en la primera línea.

Every document exists in Spanish and in English under the same file name: `docs/<name>.md` and `docs/en/<name>.md`. Both start with a language switch on the first line.

| Español | English | Qué hay dentro · What is in it |
|---|---|---|
| [`tareas.md`](tareas.md) | [`en/tareas.md`](en/tareas.md) | Las cinco tareas: prompt literal, esquema, entrada de cada caso, criterio de acierto y frase de fallo · The five tasks: verbatim prompt, schema, case input, pass criteria and failure sentence |
| [`datos.md`](datos.md) | [`en/datos.md`](en/datos.md) | Los 85 ficheros de la conservera inventada, uno a uno, y el modelo de datos · The 85 files of the invented cannery, one by one, and the data model |
| [`puntuacion.md`](puntuacion.md) | [`en/puntuacion.md`](en/puntuacion.md) | Normalización, reglas, umbrales del veredicto, coste, segundos y redondeos · Normalization, rules, verdict thresholds, cost, seconds and rounding |
| [`reproducir.md`](reproducir.md) | [`en/reproducir.md`](en/reproducir.md) | Cómo repetir la prueba con tu herramienta, con API y sin ella; referencia de la CLI · How to repeat the test with your own tool, with and without an API; CLI reference |
| [`metodologia.md`](metodologia.md) | [`en/metodologia.md`](en/metodologia.md) | Qué mide y qué no, por qué la puntuación es determinista, versionado de los datos · What it measures and what it does not, why scoring is deterministic, data versioning |

Por dónde empezar: `reproducir.md` si vas a medir algo hoy, `metodologia.md` si vas a decidir si te fías de una cifra, `tareas.md` si vas a discutir una regla concreta.

Where to start: `reproducir.md` if you are going to measure something today, `metodologia.md` if you are deciding whether to trust a number, `tareas.md` if you want to argue about a specific rule.

## Qué está solo en español · Spanish only

La prosa se traduce; lo que el programa imprime, envía o lee no. Los identificadores, los subcomandos, los nombres de fichero, las claves del JSON, los prompts de sistema y las frases de fallo están en español en los dos idiomas, porque son el objeto medido y no la envoltura.

Prose is written in each language; whatever the program prints, sends or reads is not translated. Identifiers, subcommands, file names, JSON keys, system prompts and failure sentences stay in Spanish in both versions, because they are the thing being measured, not the wrapping.

| Documento · Document | Por qué solo en español · Why Spanish only |
|---|---|
| [`../datos/README.md`](../datos/README.md) | Portada de una carpeta cuyo contenido es texto español. El resumen en inglés está en [`en/datos.md`](en/datos.md) · Front page of a folder whose content is Spanish text; the English account is in [`en/datos.md`](en/datos.md) |
| [`../resultados/README.md`](../resultados/README.md) | Reglas de publicación de un blog en español. Las cifras publicadas y cómo se leen están en [`en/metodologia.md`](en/metodologia.md) · Publishing rules of a Spanish blog; the published figures and how to read them are in [`en/metodologia.md`](en/metodologia.md) |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md), [`../CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md), [`../SECURITY.md`](../SECURITY.md) | Proceso interno. Los issues y los pull requests se aceptan en español o en inglés; los mensajes de commit son en inglés · Internal process. Issues and pull requests are accepted in Spanish or English; commit messages are in English |
| [`../CHANGELOG.md`](../CHANGELOG.md), [`../CITATION.cff`](../CITATION.cff), [`../LICENSE`](../LICENSE) | Registro, metadatos y texto legal · Log, metadata and legal text |
