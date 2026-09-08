"""Línea de órdenes del kit: ``python -m kit_pyme <orden>``.

Órdenes:

* ``tareas``: lista las cinco tareas.
* ``casos <tarea>``: imprime la entrada de cada caso, para pegarla en cualquier herramienta.
* ``prompt <tarea>``: imprime el mensaje de sistema que se envía (prompt + línea FORMATO).
* ``puntuar <tarea> <respuestas.jsonl>``: puntúa respuestas dadas (una línea JSON por caso,
  ``{"id": ..., "respuesta": ...}``) y escribe ``resultado.json`` con la forma del blog.
* ``ejecutar --tarea <id> --endpoint <url> --modelo <nombre> --clave-env <VAR>``: llama al
  modelo caso a caso, mide segundos y tokens, estima el coste y escribe ``resultado.json``.
* ``verificar``: comprueba ``datos/CHECKSUMS.sha256`` y los sha256 de los prompts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from kit_pyme import __version__
from kit_pyme.cliente import Cliente, cargar_precios, endpoint_directo
from kit_pyme.ejecutar import CONCURRENCIA, ModeloNoDisponible, ejecutar_tarea
from kit_pyme.informe import (
    Informe,
    construir_informe,
    escribir_json,
    leer_jsonl,
    registros_desde_jsonl,
    tabla,
)
from kit_pyme.tareas import ErrorTarea, Tarea, cargar_tarea, cargar_tareas, raiz_del_kit
from kit_pyme.verificar import FICHERO_CHECKSUMS, generar_checksums, verificar

#: Códigos de salida.
SALIDA_OK = 0
SALIDA_ERROR = 1
SALIDA_NO_DISPONIBLE = 3


def _imprimir(texto: str = "") -> None:
    sys.stdout.write(texto + "\n")


def _error(texto: str) -> int:
    sys.stderr.write(f"kit_pyme: {texto}\n")
    return SALIDA_ERROR


def _analizador() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m kit_pyme",
        description="El kit de la pyme: banco de pruebas del blog «A la última» de Bytenauta.",
    )
    p.add_argument("--raiz", help="carpeta con datos/ y tareas/ (por defecto se busca sola)")
    p.add_argument("--version", action="version", version=f"kit_pyme {__version__}")
    sub = p.add_subparsers(dest="orden", required=True, metavar="orden")

    sub.add_parser("tareas", help="lista las tareas del kit")

    c = sub.add_parser("casos", help="imprime la entrada de cada caso de una tarea")
    c.add_argument("tarea", help="id de la tarea (ver «tareas»)")
    c.add_argument("--id", dest="solo_id", help="solo ese caso")
    c.add_argument("--jsonl", action="store_true", help="una línea JSON {id, entrada} por caso")

    pr = sub.add_parser("prompt", help="imprime el mensaje de sistema que se envía al modelo")
    pr.add_argument("tarea", help="id de la tarea")
    pr.add_argument("--sin-formato", action="store_true", help="sin la línea FORMATO del final")

    pu = sub.add_parser("puntuar", help="puntúa respuestas dadas en un jsonl")
    pu.add_argument("tarea", help="id de la tarea")
    pu.add_argument("respuestas", help='fichero jsonl: una línea {"id", "respuesta"} por caso')
    pu.add_argument("--modelo", default="", help="nombre con el que etiquetar el resultado")
    pu.add_argument("--salida", help="carpeta donde escribir resultado.json y detalle.json")
    pu.add_argument("--json", action="store_true", help="imprime resultado.json en vez de la tabla")

    e = sub.add_parser("ejecutar", help="llama a un modelo caso a caso y escribe resultado.json")
    e.add_argument("--tarea", required=True, help="id de la tarea")
    e.add_argument("--modelo", required=True, help="id del modelo, p. ej. anthropic/claude-haiku-4-5")
    e.add_argument("--endpoint", help="URL de chat/completions compatible con OpenAI")
    e.add_argument("--clave-env", help="variable de entorno con la clave de API")
    e.add_argument("--modelo-api", help="nombre a enviar en «model» (por defecto, el id sin proveedor)")
    e.add_argument("--concurrencia", type=int, default=CONCURRENCIA, help="llamadas simultáneas (4)")
    e.add_argument("--casos", type=int, help="prueba solo los N primeros casos (muestra)")
    e.add_argument("--salida", default=".", help="carpeta donde escribir resultado.json (por defecto, aquí)")
    e.add_argument("--precios", help="tabla de precios JSON (por defecto, la del paquete)")
    e.add_argument("--novedad-url", default="", help="URL de la novedad probada, si la hay")
    e.add_argument("--tiempo-maximo", type=float, default=300.0, help="segundos de espera por respuesta")
    e.add_argument("--json", action="store_true", help="imprime resultado.json además de la tabla")

    v = sub.add_parser("verificar", help="comprueba los checksums de datos/ y los prompts")
    v.add_argument(
        "--regenerar",
        action="store_true",
        help="reescribe CHECKSUMS.sha256 con los ficheros actuales (solo al subir versión del kit)",
    )
    return p


def _orden_tareas(raiz: Path) -> int:
    tareas = cargar_tareas(raiz)
    ancho = max(len(t.id) for t in tareas)
    _imprimir(f"{'id'.ljust(ancho)}  casos  max_tokens  nombre")
    for t in tareas:
        _imprimir(f"{t.id.ljust(ancho)}  {len(t.preparar()):>5}  {t.max_tokens:>10}  {t.nombre}")
    return SALIDA_OK


def _orden_casos(tarea: Tarea, solo_id: str | None, jsonl: bool) -> int:
    casos = [c for c in tarea.preparar() if solo_id is None or c.id == solo_id]
    if solo_id is not None and not casos:
        return _error(f"no hay ningún caso «{solo_id}» en {tarea.id}")
    for c in casos:
        if jsonl:
            _imprimir(json.dumps({"id": c.id, "entrada": c.entrada}, ensure_ascii=False))
        else:
            _imprimir(f"===== {c.id} =====")
            _imprimir(c.entrada)
            _imprimir()
    return SALIDA_OK


def _orden_prompt(tarea: Tarea, sin_formato: bool) -> int:
    sys.stdout.write(tarea.prompt if sin_formato else tarea.system)
    if not tarea.prompt.endswith("\n"):
        sys.stdout.write("\n")
    return SALIDA_OK


def _mostrar(informe: Informe, salida: Path | None, como_json: bool, modelo_pedido: str) -> None:
    if como_json:
        _imprimir(json.dumps(informe.resultado, ensure_ascii=False, indent=2))
    else:
        _imprimir(tabla(informe.resultado))
    if salida is not None:
        escribir_json(salida / "resultado.json", informe.resultado)
        escribir_json(salida / "detalle.json", informe.detalle(modelo_pedido))
        _imprimir(f"Escrito {salida / 'resultado.json'} y {salida / 'detalle.json'}")


def _orden_puntuar(tarea: Tarea, ruta: Path, modelo: str, salida: Path | None, como_json: bool) -> int:
    casos = tarea.preparar()
    filas = leer_jsonl(ruta)
    registros = registros_desde_jsonl(tarea, casos, filas)
    segundos = sum(r.segundos for r in registros)
    informe = construir_informe(tarea, casos, registros, round(segundos, 1), modelo)
    _mostrar(informe, salida, como_json, modelo)
    return SALIDA_OK


def _orden_ejecutar(tarea: Tarea, a: argparse.Namespace) -> int:
    endpoint = a.endpoint or endpoint_directo(a.modelo)
    if not endpoint:
        return _error(f"no sé el endpoint de «{a.modelo}»: pásalo con --endpoint")
    clave = ""
    if a.clave_env:
        clave = os.environ.get(a.clave_env, "")
        if not clave:
            return _error(f"la variable de entorno {a.clave_env} está vacía o no existe")
    precios = cargar_precios(Path(a.precios) if a.precios else None)
    cliente = Cliente(endpoint=endpoint, clave=clave, precios=precios, tiempo_maximo=a.tiempo_maximo)
    casos = tarea.preparar()
    modo_barato = a.casos is not None and a.casos < len(casos)
    if a.casos is not None:
        casos = casos[: max(0, a.casos)]
    _imprimir(f"{tarea.id}: {len(casos)} casos contra {a.modelo} en {endpoint} (concurrencia {a.concurrencia})")
    try:
        informe = ejecutar_tarea(
            cliente,
            tarea,
            a.modelo,
            modelo_api=a.modelo_api,
            casos=casos,
            concurrencia=a.concurrencia,
            novedad_url=a.novedad_url,
            modo_barato=modo_barato,
        )
    except ModeloNoDisponible as e:
        sys.stderr.write(f"kit_pyme: {e}\n")
        if e.error.cuerpo:
            sys.stderr.write(f"  respuesta: {e.error.cuerpo[:300]}\n")
        return SALIDA_NO_DISPONIBLE
    _mostrar(informe, Path(a.salida), a.json, a.modelo)
    if not a.json:
        _imprimir(
            f"Tokens: {informe.uso.tokens_entrada} de entrada, {informe.uso.tokens_salida} de salida"
            f" (coste sin redondear {informe.uso.coste_eur:.6f} €)"
        )
    return SALIDA_OK


def _orden_verificar(raiz: Path, regenerar: bool) -> int:
    ruta = raiz / "datos" / FICHERO_CHECKSUMS
    if regenerar:
        contenido = generar_checksums(raiz)
        with open(ruta, "w", encoding="utf-8", newline="\n") as f:
            f.write(contenido)
        _imprimir(f"Reescrito {ruta} ({contenido.count(chr(10))} ficheros). Recuerda subir la versión en CHANGELOG.md.")
    problemas = verificar(raiz)
    if problemas:
        for p in problemas:
            _imprimir(f"MAL  {p}")
        _imprimir(f"{len(problemas)} problema(s): los datos NO son los publicados.")
        return SALIDA_ERROR
    _imprimir("OK   datos/ y los prompts son los publicados (checksums y sha256 correctos).")
    return SALIDA_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada de la CLI.

    Args:
        argv: Argumentos (sin el nombre del programa); ``None`` para ``sys.argv``.

    Returns:
        Código de salida.
    """
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    a = _analizador().parse_args(argv)
    try:
        raiz = raiz_del_kit(a.raiz)
        if a.orden == "tareas":
            return _orden_tareas(raiz)
        if a.orden == "verificar":
            return _orden_verificar(raiz, a.regenerar)
        tarea = cargar_tarea(a.tarea, raiz)
        if a.orden == "casos":
            return _orden_casos(tarea, a.solo_id, a.jsonl)
        if a.orden == "prompt":
            return _orden_prompt(tarea, a.sin_formato)
        if a.orden == "puntuar":
            return _orden_puntuar(tarea, Path(a.respuestas), a.modelo, Path(a.salida) if a.salida else None, a.json)
        if a.orden == "ejecutar":
            return _orden_ejecutar(tarea, a)
    except (ErrorTarea, OSError, ValueError) as e:
        return _error(str(e))
    return _error(f"orden desconocida: {a.orden}")


if __name__ == "__main__":
    sys.exit(main())
