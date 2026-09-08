"""Las cinco tareas del kit: carga ``tareas/<id>/tarea.json`` y construye los casos desde ``datos/``.

Cada ``tarea.json`` lleva el prompt de sistema literal de ``src/pruebas/tareas.ts`` del
blog, con marcadores ``{{datos/...}}`` allí donde el TypeScript interpola un fichero
(tarifa, clientes, registro previo, contrato). Al componer el prompt se sustituyen por el
contenido del fichero tal cual (UTF-8, saltos de línea sin tocar), y un test comprueba
que el sha256 del resultado es el del prompt que envía el blog.

La ``entrada`` de cada caso (el mensaje de usuario) se construye según lo que declara
``tarea.json``: el fichero entero de la carpeta (pedidos, correos, facturas), un campo del
fichero de verdad (la pregunta del contrato) o una plantilla rellenada con el caso
(recordatorios).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kit_pyme import javascript as js
from kit_pyme.esquema import con_claves_explicitas

#: Orden canónico de las tareas, el mismo que ``IDS_TAREAS`` en el blog.
ORDEN_TAREAS = (
    "extraer-pedidos",
    "resumir-correos",
    "buscar-en-contrato",
    "clasificar-facturas",
    "redactar-recordatorio",
)

#: Variable de entorno que fija la raíz del kit (donde están ``datos/`` y ``tareas/``).
VARIABLE_RAIZ = "KIT_PYME_RAIZ"

_MARCADOR_RE = re.compile(r"\{\{([^{}]+)\}\}")


class ErrorTarea(ValueError):
    """Una tarea no existe o su ``tarea.json`` está mal formado."""


@dataclass
class Caso:
    """Un caso de una tarea.

    Attributes:
        id: Identificador (``pedido-01``, ``p07``, ``recordatorio-03``…).
        entrada: Lo que se da al modelo como mensaje de usuario.
        esperado: La respuesta correcta tal cual viene del ``*-verdad.json``.
    """

    id: str
    entrada: str
    esperado: dict[str, Any]


@dataclass
class Tarea:
    """Una tarea del kit, ya cargada y con el prompt compuesto.

    Attributes:
        id: Identificador de la tarea.
        nombre: Nombre legible («Sacar las líneas de 20 pedidos tal como llegan por correo»).
        descripcion: Una frase para el lector: qué se mide y por qué importa en una pyme.
        prompt: Prompt de sistema con los ficheros ya interpolados.
        esquema: JSON Schema de la respuesta.
        max_tokens: Tope de tokens de salida que se pide al modelo.
        linea_formato: Si se añade al prompt la línea FORMATO con las claves del esquema.
        verdad: Contenido del ``*-verdad.json`` de la tarea.
        clave_lista: Clave del ``verdad`` donde está la lista de casos.
        entrada: Cómo se construye la entrada de cada caso.
        raiz: Raíz del kit.
    """

    id: str
    nombre: str
    descripcion: str
    prompt: str
    esquema: dict[str, Any]
    max_tokens: int
    linea_formato: bool
    verdad: dict[str, Any]
    clave_lista: str
    entrada: dict[str, Any]
    raiz: Path
    _casos: list[Caso] | None = field(default=None, repr=False)

    @property
    def system(self) -> str:
        """El mensaje de sistema que se envía de verdad: prompt más la línea FORMATO."""
        return con_claves_explicitas(self.prompt, self.esquema) if self.linea_formato else self.prompt

    def preparar(self) -> list[Caso]:
        """Construye los casos en el orden del fichero de verdad.

        Returns:
            Lista de casos con su entrada y su respuesta esperada.
        """
        if self._casos is None:
            elementos = self.verdad.get(self.clave_lista)
            if not isinstance(elementos, list):
                raise ErrorTarea(f"{self.id}: el fichero de verdad no tiene la lista «{self.clave_lista}»")
            self._casos = [Caso(id=str(e["id"]), entrada=self._entrada(e), esperado=e) for e in elementos]
        return list(self._casos)

    def _entrada(self, caso: dict[str, Any]) -> str:
        tipo = self.entrada.get("tipo")
        if tipo == "fichero":
            ruta = self.raiz / self.entrada["carpeta"] / str(caso[self.entrada["campo"]])
            return leer_texto(ruta)
        if tipo == "campo":
            return str(caso[self.entrada["campo"]])
        if tipo == "plantilla":
            return _rellenar_plantilla(self, caso)
        raise ErrorTarea(f"{self.id}: tipo de entrada desconocido «{tipo}»")


def leer_texto(ruta: Path) -> str:
    """Lee un fichero de texto del kit sin traducir los saltos de línea.

    Args:
        ruta: Ruta del fichero (UTF-8, LF).

    Returns:
        El contenido íntegro.
    """
    with open(ruta, encoding="utf-8", newline="") as f:
        return f.read()


def leer_json(ruta: Path) -> Any:
    """Lee un fichero JSON del kit.

    Args:
        ruta: Ruta del fichero.

    Returns:
        El valor parseado.
    """
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def raiz_del_kit(explicita: str | os.PathLike[str] | None = None) -> Path:
    """Localiza la raíz del kit: la carpeta que contiene ``datos/`` y ``tareas/``.

    El orden es: la ruta explícita, la variable de entorno ``KIT_PYME_RAIZ``, el directorio
    actual o alguno de sus padres, y por último la carpeta que contiene este paquete (el
    caso normal cuando se ejecuta desde el clon del repositorio).

    Args:
        explicita: Ruta dada por el usuario (``--raiz``), si la hay.

    Returns:
        La raíz del kit.

    Raises:
        ErrorTarea: Si no se encuentra ninguna carpeta con ``datos/`` y ``tareas/``.
    """
    candidatas: list[Path] = []
    if explicita:
        # Una raíz dada a mano se respeta o se falla: buscar en otro sitio a espaldas de quien
        # la pasó acabaría midiendo con datos distintos de los que pidió.
        dada = Path(explicita)
        if not ((dada / "datos").is_dir() and (dada / "tareas").is_dir()):
            raise ErrorTarea(f"en {dada} no hay un kit (falta datos/ o tareas/)")
        return dada.resolve()
    if os.environ.get(VARIABLE_RAIZ):
        candidatas.append(Path(os.environ[VARIABLE_RAIZ]))
    actual = Path.cwd()
    candidatas.extend([actual, *actual.parents])
    candidatas.append(Path(__file__).resolve().parent.parent)
    for c in candidatas:
        if (c / "datos").is_dir() and (c / "tareas").is_dir():
            return c.resolve()
    raise ErrorTarea("no encuentro la raíz del kit (una carpeta con datos/ y tareas/); usa --raiz")


def ids_tareas(raiz: Path) -> list[str]:
    """Lista los identificadores de las tareas disponibles, en el orden canónico.

    Args:
        raiz: Raíz del kit.

    Returns:
        Los ids de las carpetas de ``tareas/`` que tienen ``tarea.json``.
    """
    presentes = {p.name for p in (raiz / "tareas").iterdir() if (p / "tarea.json").is_file()}
    conocidas = [t for t in ORDEN_TAREAS if t in presentes]
    return conocidas + sorted(presentes - set(ORDEN_TAREAS))


def componer_prompt(plantilla: str, raiz: Path) -> str:
    """Sustituye cada ``{{ruta}}`` por el contenido del fichero, sin tocar nada más.

    Args:
        plantilla: Prompt con marcadores.
        raiz: Raíz del kit, respecto a la que se resuelven las rutas.

    Returns:
        El prompt compuesto, byte a byte igual al del blog.
    """
    return _MARCADOR_RE.sub(lambda m: leer_texto(raiz / m.group(1).strip()), plantilla)


def cargar_tarea(id_tarea: str, raiz: Path | None = None) -> Tarea:
    """Carga ``tareas/<id>/tarea.json`` y compone su prompt.

    Args:
        id_tarea: Identificador de la tarea.
        raiz: Raíz del kit; si no se da, se localiza con ``raiz_del_kit``.

    Returns:
        La tarea lista para preparar casos.

    Raises:
        ErrorTarea: Si la tarea no existe o le falta algún campo.
    """
    raiz = raiz or raiz_del_kit()
    ruta = raiz / "tareas" / id_tarea / "tarea.json"
    if not ruta.is_file():
        raise ErrorTarea(f"tarea desconocida: {id_tarea} (no existe {ruta})")
    d = leer_json(ruta)
    obligatorios = (
        "id",
        "nombre",
        "descripcion",
        "prompt",
        "esquema",
        "max_tokens",
        "verdad",
        "lista",
        "entrada",
    )
    faltan = [k for k in obligatorios if k not in d]
    if faltan:
        raise ErrorTarea(f"{id_tarea}: a tarea.json le faltan {', '.join(faltan)}")
    if d["id"] != id_tarea:
        raise ErrorTarea(f"{id_tarea}: tarea.json dice id «{d['id']}»")
    return Tarea(
        id=d["id"],
        nombre=d["nombre"],
        descripcion=d["descripcion"],
        prompt=componer_prompt(d["prompt"], raiz),
        esquema=d["esquema"],
        max_tokens=int(d["max_tokens"]),
        linea_formato=bool(d.get("linea_formato", True)),
        verdad=leer_json(raiz / d["verdad"]),
        clave_lista=d["lista"],
        entrada=d["entrada"],
        raiz=raiz,
    )


def cargar_tareas(raiz: Path | None = None) -> list[Tarea]:
    """Carga todas las tareas del kit en orden canónico.

    Args:
        raiz: Raíz del kit; si no se da, se localiza con ``raiz_del_kit``.

    Returns:
        Las tareas.
    """
    raiz = raiz or raiz_del_kit()
    return [cargar_tarea(i, raiz) for i in ids_tareas(raiz)]


def fecha_es(iso: str) -> str:
    """``2026-09-07`` → ``07/09/2026`` (lo que hace ``split('-').reverse().join('/')``).

    Args:
        iso: Fecha en AAAA-MM-DD.

    Returns:
        La fecha en DD/MM/AAAA.
    """
    return "/".join(reversed(iso.split("-")))


def _fila_cobro(csv: str, numero: str) -> str:
    """Cabecera del CSV más la fila de la factura, o ``(no encontrada)``."""
    lineas = re.split(r"\r?\n", csv)
    fila = next((ln for ln in lineas if ln.startswith(numero + ";")), None)
    return f"{lineas[0]}\n{fila}" if fila is not None else "(no encontrada)"


def _rellenar_plantilla(tarea: Tarea, caso: dict[str, Any]) -> str:
    """Construye la entrada de un recordatorio igual que ``tareas.ts`` (líneas 345-362)."""
    e = tarea.entrada
    valores: dict[str, Any] = {k: v for k, v in caso.items() if not isinstance(v, dict | list)}
    valores["importe_pendiente"] = js.a_fijo(float(caso["importe_pendiente"]), 2).replace(".", ",")
    valores["vencimiento"] = fecha_es(str(caso["vencimiento"]))
    relacionados = tarea.verdad.get(e.get("rasgos_de", "recordar")) or []
    clave = e.get("clave_relacion", "factura")
    encontrado = next((r for r in relacionados if r.get(clave) == caso.get(clave)), None)
    valores["rasgos"] = (encontrado or {}).get("rasgos", "")
    if "fila_de" in e:
        csv = leer_texto(tarea.raiz / e["fila_de"])
        valores["fila_cobros"] = _fila_cobro(csv, str(caso[clave]))
    return str(e["plantilla"]).format_map(valores)
