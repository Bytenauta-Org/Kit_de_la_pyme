# Seguridad

*In English: this policy is kept in Spanish. The short version: the repository contains no real data and no secrets, the runner only calls the endpoint you pass in `--endpoint` with the key it reads from the environment variable you name in `--clave-env`, and it never prints or stores that key. To report a vulnerability, do not open a public issue: use «Report a vulnerability» on the Security tab, or write to info@bytenauta.com with the subject `Seguridad: Kit de la pyme`. What the runner does and does not send is described in [`docs/en/reproducir.md`](docs/en/reproducir.md).*

## Qué hay y qué no hay en este repositorio

- **No hay datos reales.** Todo lo que hay en `datos/` es inventado: empresas, personas, NIF, cuentas bancarias, direcciones y correos (`.example`). Si encuentras algo que coincida con una empresa o persona real, avísanos como se indica abajo y lo cambiaremos en la siguiente versión.
- **No hay secretos.** El repositorio no contiene claves de API ni credenciales, y la CI no las necesita: los tests usan un servidor falso en `127.0.0.1`.
- **El ejecutor no envía nada a Bytenauta.** `python -m kit_pyme ejecutar` hace peticiones HTTP solo al endpoint que tú indicas con `--endpoint`, con la clave que lee de la variable de entorno que indicas con `--clave-env`. No hay telemetría ni llamadas a ningún otro servidor. `puntuar`, `casos`, `tareas` y `verificar` no hacen ninguna conexión.
- **La clave no se escribe.** El ejecutor no imprime la clave ni la guarda en `resultado.json` ni en el detalle de la ejecución.

## Qué consideramos una vulnerabilidad

- Que la clave de API acabe en pantalla, en un fichero de salida, en un log o en una petición a un host distinto del endpoint indicado.
- Que un fichero de entrada controlado por terceros (`respuestas.jsonl`, `tarea.json`, `precios.json`, `CHECKSUMS.sha256`) permita ejecutar código, leer o escribir fuera del directorio de trabajo, o alterar la puntuación sin que se note.
- Que `verificar` dé por buenos ficheros alterados.
- Que el servidor falso de los tests escuche en una interfaz distinta de `127.0.0.1`.
- Cualquier dependencia o acción de la CI que descargue y ejecute código sin fijar versión.

Lo que no es una vulnerabilidad: que un modelo devuelva una respuesta incorrecta, que un endpoint de terceros retenga los datos que le envías (es su política, no la nuestra; léela antes de ejecutar), o que el coste estimado no coincida con la factura del proveedor.

## Cómo avisar

No abras un issue público para un problema de seguridad. Usa uno de estos dos canales:

1. **Aviso privado en GitHub**: en la pestaña «Security» del repositorio, «Report a vulnerability».
2. **Correo** a **info@bytenauta.com** con el asunto `Seguridad: Kit de la pyme`. Si necesitas cifrar el mensaje, pídenos una clave por ese mismo correo.

Incluye qué has encontrado, cómo reproducirlo (comando, fichero de entrada, versión del kit y de Python) y qué impacto crees que tiene.

## Qué puedes esperar

- Acuse de recibo en 5 días laborables.
- Evaluación y respuesta con un plan (corrección, mitigación o explicación de por qué no lo consideramos un problema) en 15 días laborables.
- Corrección publicada con una entrada en `CHANGELOG.md` que te acredita si quieres.

No hay programa de recompensas. Bytenauta S.L. es una empresa pequeña; lo que ofrecemos es rapidez y crédito público.

## Versiones con soporte

| Versión | Soporte |
|---|---|
| 1.x | Sí |
| Anteriores a la publicación del repositorio (el zip del kit) | No: usa el repositorio |

## Recomendaciones para quien ejecuta el kit

- Guarda la clave en una variable de entorno de la sesión, no en un fichero del repositorio ni en el historial de la shell si puedes evitarlo.
- Antes de enviar el contrato o las facturas a un endpoint, recuerda que aunque los datos sean inventados, el proveedor los recibe y puede retenerlos según su política.
- Si ejecutas contra un servidor local, comprueba en qué interfaz escucha.
- Revisa `precios.json` y `tareas/*/tarea.json` si vienen de un fork que no controlas: son ficheros de datos, pero deciden el coste y el prompt.
