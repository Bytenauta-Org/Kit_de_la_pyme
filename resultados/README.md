# Resultados publicados

*In English: these are the publishing rules of a Spanish blog, so they are kept in Spanish. What the published figures mean and how to read them is in [`../docs/en/metodologia.md`](../docs/en/metodologia.md).*

Esta carpeta guarda, número a número, las cifras que el blog «A la última» ha publicado sobre el kit, tal como salieron y con su procedencia. Es el registro contra el que se compara cualquier resultado nuevo.

## La regla

**Cada número del blog que publique cifras medidas sobre el kit añade su fichero aquí**, `AAAA-Www.json` (semana ISO del número), en el mismo commit o en el siguiente a la publicación. El fichero no se edita después: si el blog rectifica una cifra, se añade `AAAA-Www-rectificacion.json` con la cifra nueva y el motivo, y el original se queda.

Un resultado siempre dice con qué versión de datos se midió (`kit_datos_version`). Cuando los datos suban de versión mayor, los ficheros anteriores siguen aquí con su versión y no se comparan con los nuevos.

## Formato

Un sobre con la procedencia y, dentro, la lista de pruebas con la misma forma que publica el blog (`ResultadoPrueba`):

```json
{
  "semana": "2026-W37",
  "fecha_publicacion": "2026-09-08",
  "publicado_en": "https://bytenauta.com/a-la-ultima/",
  "numero": "<slug del número>",
  "origen": "<repositorio y commit de donde salen las cifras>",
  "banco": "<qué código las midió y desde dónde>",
  "modo": "<condiciones: endpoint, response_format, temperatura, concurrencia, intentos>",
  "kit_datos_version": "1.0.0",
  "pruebas": [
    {
      "novedad_url": "",
      "modelo": "anthropic/claude-haiku-4-5",
      "tarea": "extraer-pedidos",
      "tarea_nombre": "Sacar las líneas de 20 pedidos tal como llegan por correo",
      "casos": 20,
      "aciertos": 15,
      "fallos": ["...", "...", "..."],
      "segundos": 16.9,
      "coste_eur": 0.3822,
      "veredicto": "todavia-no",
      "nota": "...",
      "de_fondo": true,
      "nombre_visible": "el modelo pequeño de Anthropic"
    }
  ]
}
```

Campos de cada prueba, en el orden en que los escribe el blog:

| Campo | Qué es |
|---|---|
| `novedad_url` | URL de la novedad de la semana que motivó la prueba; vacío si la prueba es de la cola de fondo |
| `modelo` | Id con el que se llamó (`proveedor/modelo`) o el nombre de la herramienta si la prueba fue manual |
| `tarea`, `tarea_nombre` | Id y nombre de la tarea; con `(muestra de N casos)` si se probó una muestra |
| `casos`, `aciertos`, `fallos` | Casos probados, aciertos y hasta tres fallos en una frase |
| `segundos` | Tiempo de pared del lote con cuatro casos en vuelo, un decimal |
| `coste_eur` | Coste estimado, cuatro decimales |
| `veredicto`, `nota` | Por reglas; ver [`docs/puntuacion.md`](../docs/puntuacion.md) |
| `sin_respuesta`, `errores_servicio` | Solo si son mayores que cero |
| `manual` | `true` si la probó una persona con una herramienta sin API |
| `de_fondo`, `nombre_visible` | `true` y el nombre sin marca cuando la prueba viene de la cola de cosas pendientes y no de una novedad de la semana |

Opcionalmente, `otras_tiradas` recoge tiradas del mismo día que no se publicaron, con sus segundos y coste, para que se vea la variabilidad; y `nota_tiradas` la explica.

## Ficheros

| Fichero | Número | Modelo | Pruebas | Datos |
|---|---|---|---|---|
| [`2026-W37.json`](2026-W37.json) | 2026-09-08, primer número | anthropic/claude-haiku-4-5 | extraer-pedidos 15/20 (16,9 s, 0,3822 €, todavia-no); clasificar-facturas 24/25 (10,5 s, 0,1428 €, lo-usaria-el-lunes) | 1.0.0 |

Sobre 2026-W37: el mismo modelo se ejecutó tres veces ese día mientras se ponía a punto el pipeline, con los mismos aciertos y los mismos fallos las tres veces; los segundos y la cuarta cifra decimal del coste cambiaron. El fichero recoge la tirada publicada (la del PR #5 de la web) y anota las otras dos.

## Resultados de terceros

Si repites una prueba con tu herramienta y quieres que conste, abre un issue con la plantilla «Resultado con tu herramienta». Los resultados que sigan el procedimiento de [`docs/reproducir.md`](../docs/reproducir.md) (datos verificados, prompt y esquema sin cambios, puntuación del kit) se guardan en `resultados/terceros/AAAA-MM-DD-<herramienta>.json` con el mismo sobre, más `medido_por` (quien lo envía, si quiere constar), `con_api` (`true` o `false`) y `desviaciones` (una lista con lo que se hizo distinto, o vacía). No se aceptan resultados sin el `resultado.json` del kit ni con datos de otra versión que la indicada.
