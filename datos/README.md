# Datos del kit de la pyme · v1.0.0

Todo lo que hay aquí es de **Conservas Marjal Blanca S.L.**, una conservera inventada de Almoradí
(Alicante) con unos 40 empleados. Clientes, proveedores, NIF, cuentas bancarias, direcciones e
importes son inventados pero coherentes: los NIF llevan dígito de control válido, los precios cuadran
con la tarifa, los dominios de correo terminan en `.example`. Ninguna empresa ni persona es real.

| Carpeta     | Ficheros                                        | Casos | Respuesta correcta         |
|-------------|-------------------------------------------------|------:|----------------------------|
| `pedidos/`  | `pedido-01…20.txt`, `tarifa.csv`, `clientes.csv` |    20 | `pedidos-verdad.json`      |
| `correos/`  | `correo-01…30.txt`                               |    30 | `correos-verdad.json`      |
| `contrato/` | `contrato.txt` (28.396 palabras)                 |    15 | `contrato-preguntas.json`  |
| `facturas/` | `factura-01…25.txt`, `registro-previo.csv`       |    25 | `facturas-verdad.json`     |
| `cobros/`   | `cobros.csv` (60 facturas emitidas)              |    10 | `cobros-verdad.json`       |

85 ficheros en total, todos UTF-8 sin BOM y con salto de línea LF. Los CSV van con `;` y coma decimal.
Cada `*-verdad.json` explica en su campo `_comentario` el criterio de acierto; el criterio exacto,
regla por regla, está en [`../docs/puntuacion.md`](../docs/puntuacion.md).

Fechas de referencia: los pedidos llegan el jueves 10/09/2026; los correos se leen y los cobros se
reclaman el lunes 14/09/2026. Están dentro de los prompts, así que no cambian.

## Versión de los datos

**v1.0.0** son los datos con los que el blog publicó sus primeras cifras (semana 2026-W37). Se
versionan con [SemVer](https://semver.org/lang/es/) y la regla es simple: **cualquier byte de las
cinco carpetas de datos que cambie sube la versión** y se anota en [`../CHANGELOG.md`](../CHANGELOG.md).

- *Mayor*: cambia un caso, una respuesta correcta o un fichero de apoyo (`tarifa.csv`,
  `clientes.csv`, `registro-previo.csv`, `cobros.csv`, `contrato.txt`). Las cifras dejan de ser
  comparables con las anteriores.
- *Menor*: entran casos o carpetas nuevos sin tocar los que había.
- *Parche*: solo cambian `README.md`, `esquemas/` o la documentación; los 85 ficheros siguen iguales.

Los resultados publicados en [`../resultados/`](../resultados/) dicen con qué versión se midieron.

## Verificar que tienes los datos buenos

`CHECKSUMS.sha256` sella los 85 ficheros (formato de `sha256sum`, rutas relativas a esta carpeta).
Cualquiera de las dos órdenes vale:

```bash
cd datos && sha256sum -c CHECKSUMS.sha256
python tools/verificar_checksums.py          # desde la raíz del repositorio; avisa también de ficheros que sobran
```

Si se cambia algo (y por tanto la versión), `python tools/verificar_checksums.py --escribir`
regenera el sello.

## Esquemas

`esquemas/` lleva un JSON Schema (draft 2020-12) por cada fichero:

| Esquema                                  | Describe                                                          |
|------------------------------------------|-------------------------------------------------------------------|
| `pedidos-verdad.schema.json`             | `pedidos/pedidos-verdad.json`                                     |
| `correos-verdad.schema.json`             | `correos/correos-verdad.json`                                     |
| `contrato-preguntas.schema.json`         | `contrato/contrato-preguntas.json`                                |
| `facturas-verdad.schema.json`            | `facturas/facturas-verdad.json`                                   |
| `cobros-verdad.schema.json`              | `cobros/cobros-verdad.json`                                       |
| `respuesta-<tarea>.schema.json` (cinco)  | La respuesta que se le pide al modelo en cada caso de esa tarea   |

Los cinco esquemas de respuesta son **copia literal** del esquema que el blog manda con cada tarea
(`src/pruebas/tareas.ts` del pipeline): el objeto que viaja al modelo y contra el que se valida su
respuesta es el fichero sin las claves de metadatos `$schema`, `$id`, `title` y `$comment`. Es el
mismo objeto que lleva `tareas/<id>/tarea.json`.

Para comprobar que los ficheros de verdad cumplen sus esquemas y que son coherentes entre sí (precios
de tarifa, totales de facturas, registro previo, hoja de cobros):

```bash
python tools/validar_esquemas.py
```

No necesita nada fuera de la biblioteca estándar; si `jsonschema` está instalado lo usa. También
sirve para validar una respuesta de tu herramienta contra el esquema de su tarea:

```bash
python tools/validar_esquemas.py respuesta.json datos/esquemas/respuesta-clasificar-facturas.schema.json
```

## Licencia

Kit de la pyme © 2026 Bytenauta S.L., [CC BY 4.0](../LICENSE). Puedes copiarlo, redistribuirlo y
adaptarlo, también con fines comerciales, citando «Kit de la pyme, Bytenauta S.L.» y enlazando la
licencia. Sin garantía de ningún tipo: son datos inventados para probar herramientas, no
asesoramiento contable, fiscal ni jurídico.
