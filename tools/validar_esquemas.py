"""Valida los ficheros de verdad de ``datos/`` contra los JSON Schema de ``datos/esquemas/``.

Usa ``jsonschema`` (Draft 2020-12) si está instalado y, si no, un validador mínimo propio que
cubre las palabras clave que usan estos esquemas: ``type``, ``enum``, ``const``, ``required``,
``properties``, ``additionalProperties``, ``items``, ``minItems``, ``maxItems``, ``uniqueItems``,
``minimum``, ``maximum``, ``exclusiveMinimum``, ``exclusiveMaximum``, ``minLength``, ``maxLength``,
``pattern``, ``format`` (solo ``date``), ``anyOf``, ``oneOf``, ``allOf``, ``not``, ``$ref`` (solo
referencias locales ``#/…``) y ``$defs``. Después de los esquemas comprueba una lista de
invariantes entre ficheros que un esquema no puede expresar: los precios de
``pedidos-verdad.json`` son los de ``tarifa.csv``, el total de cada factura cuadra, las duplicadas
están en ``registro-previo.csv``, los casos de recordatorio salen de ``cobros.csv``…

Uso::

    python tools/validar_esquemas.py                   # los cinco ficheros de verdad + invariantes
    python tools/validar_esquemas.py --minimo          # fuerza el validador propio
    python tools/validar_esquemas.py --sin-invariantes
    python tools/validar_esquemas.py r.json datos/esquemas/respuesta-<tarea>.schema.json

Código de salida: 0 válido, 1 inválido, 2 no se pudo leer algo. Solo biblioteca estándar
(Python 3.11 o posterior); ``jsonschema`` es opcional.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import unquote

try:
    import jsonschema  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - depende del entorno
    jsonschema = None

Json = Any
"""Cualquier valor que salga de ``json.loads``."""

DATOS_POR_DEFECTO = Path(__file__).resolve().parent.parent / "datos"
TOLERANCIA = 0.011
"""Tolerancia en euros con la que puntúa el blog (dos decimales más un pelo)."""

PAREJAS: tuple[tuple[str, str, str], ...] = (
    ("pedidos/pedidos-verdad.json", "esquemas/pedidos-verdad.schema.json", "pedidos"),
    ("correos/correos-verdad.json", "esquemas/correos-verdad.schema.json", "correos"),
    ("contrato/contrato-preguntas.json", "esquemas/contrato-preguntas.schema.json", "preguntas"),
    ("facturas/facturas-verdad.json", "esquemas/facturas-verdad.schema.json", "facturas"),
    ("cobros/cobros-verdad.json", "esquemas/cobros-verdad.schema.json", "casos_recordatorio"),
)
"""Fichero de verdad, su esquema y la clave de la lista de casos."""

TAREAS: tuple[str, ...] = (
    "extraer-pedidos",
    "resumir-correos",
    "buscar-en-contrato",
    "clasificar-facturas",
    "redactar-recordatorio",
)
DRAFT = "https://json-schema.org/draft/2020-12/schema"
_FECHA_ISO = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


# ----------------------------------------------------------------- utilidades JSON


def _es_numero(valor: Json) -> bool:
    """True para int y float; false para bool, que en JSON es otro tipo."""
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _es_tipo(valor: Json, tipo: str) -> bool:
    """Comprueba un nombre de tipo de JSON Schema (``1.0`` cuenta como ``integer``)."""
    if tipo == "integer":
        return _es_numero(valor) and float(valor).is_integer()
    if tipo == "number":
        return _es_numero(valor)
    if tipo == "boolean":
        return isinstance(valor, bool)
    if tipo == "null":
        return valor is None
    if tipo == "string":
        return isinstance(valor, str)
    if tipo == "array":
        return isinstance(valor, list)
    if tipo == "object":
        return isinstance(valor, dict)
    raise ValueError(f"Tipo desconocido en el esquema: {tipo!r}")


def _nombre_tipo(valor: Json) -> str:
    """El nombre JSON Schema del tipo de un valor, para los mensajes."""
    for tipo in ("null", "boolean", "integer", "number", "string", "array", "object"):
        if _es_tipo(valor, tipo):
            return tipo
    return type(valor).__name__


def _canon(valor: Json) -> str:
    """Forma canónica para comparar como JSON.

    ``1`` y ``1.0`` son iguales; ``1`` y ``true``, distintos.
    """
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    elif isinstance(valor, list):
        return "[" + ",".join(_canon(e) for e in valor) + "]"
    elif isinstance(valor, dict):
        return "{" + ",".join(f"{json.dumps(k)}:{_canon(v)}" for k, v in sorted(valor.items())) + "}"
    return json.dumps(valor, ensure_ascii=False)


def _iguales(a: Json, b: Json) -> bool:
    """Igualdad con la semántica de JSON Schema."""
    return _canon(a) == _canon(b)


def _json(valor: Json, maximo: int = 80) -> str:
    """El valor como JSON de una línea, recortado para los mensajes."""
    texto = json.dumps(valor, ensure_ascii=False)
    return texto if len(texto) <= maximo else texto[: maximo - 1] + "…"


# ----------------------------------------------------------------- validador mínimo


class ValidadorMinimo:
    """Validador de JSON Schema 2020-12 reducido a lo que usan los esquemas del kit.

    No pretende ser completo: cubre las palabras clave listadas en la cabecera del módulo y trata
    cualquier otra como anotación (la ignora), igual que hace el estándar con las desconocidas.
    Con ``jsonschema`` instalado no se usa.
    """

    def __init__(self, esquema: dict[str, Json]) -> None:
        """Guarda el esquema raíz, que es donde se resuelven las referencias ``#/…``.

        Args:
            esquema: El esquema completo.
        """
        self.raiz = esquema

    def errores(self, valor: Json, esquema: Json | None = None, ruta: str = "$") -> list[str]:
        """Devuelve los fallos de ``valor`` contra ``esquema`` (lista vacía si es válido).

        Args:
            valor: Documento (o fragmento) a validar.
            esquema: Subesquema; ``None`` para usar la raíz.
            ruta: Ruta JSON del fragmento, para los mensajes.

        Returns:
            Mensajes ``ruta: explicación``, en el orden en que se encuentran.
        """
        if esquema is None:
            esquema = self.raiz
        if esquema is True:
            return []
        if esquema is False:
            return [f"{ruta}: no se admite ningún valor aquí"]
        fallos: list[str] = []
        if "$ref" in esquema:
            fallos += self.errores(valor, self._resolver(esquema["$ref"]), ruta)
        fallos += self._tipo(valor, esquema, ruta)
        if "enum" in esquema and not any(_iguales(valor, e) for e in esquema["enum"]):
            fallos.append(f"{ruta}: {_json(valor)} no está entre {_json(esquema['enum'])}")
        if "const" in esquema and not _iguales(valor, esquema["const"]):
            fallos.append(f"{ruta}: vale {_json(valor)} y tiene que ser {_json(esquema['const'])}")
        if isinstance(valor, dict):
            fallos += self._objeto(valor, esquema, ruta)
        elif isinstance(valor, list):
            fallos += self._lista(valor, esquema, ruta)
        elif isinstance(valor, str):
            fallos += self._cadena(valor, esquema, ruta)
        elif _es_numero(valor):
            fallos += self._numero(valor, esquema, ruta)
        fallos += self._combinaciones(valor, esquema, ruta)
        return fallos

    def _resolver(self, ref: str) -> Json:
        """Sigue una referencia local (``#/$defs/nombre``) dentro del esquema raíz."""
        if not ref.startswith("#"):
            raise ValueError(f"Solo se resuelven referencias locales, no {ref!r}")
        nodo: Json = self.raiz
        for parte in ref[1:].split("/")[1:]:
            clave = unquote(parte).replace("~1", "/").replace("~0", "~")
            nodo = nodo[int(clave)] if isinstance(nodo, list) else nodo[clave]
        return nodo

    @staticmethod
    def _tipo(valor: Json, esquema: dict[str, Json], ruta: str) -> list[str]:
        tipos = esquema.get("type")
        if tipos is None:
            return []
        lista = tipos if isinstance(tipos, list) else [tipos]
        if any(_es_tipo(valor, t) for t in lista):
            return []
        return [f"{ruta}: es {_nombre_tipo(valor)} y tiene que ser {' o '.join(lista)}"]

    def _objeto(self, valor: dict[str, Json], esquema: dict[str, Json], ruta: str) -> list[str]:
        fallos = [f"{ruta}: falta la clave «{c}»" for c in esquema.get("required", []) if c not in valor]
        propiedades: dict[str, Json] = esquema.get("properties", {})
        for clave, sub in propiedades.items():
            if clave in valor:
                fallos += self.errores(valor[clave], sub, f"{ruta}.{clave}")
        extra = esquema.get("additionalProperties", True)
        if extra is not True:
            for clave, contenido in valor.items():
                if clave in propiedades:
                    continue
                if extra is False:
                    fallos.append(f"{ruta}: la clave «{clave}» no está prevista")
                else:
                    fallos += self.errores(contenido, extra, f"{ruta}.{clave}")
        return fallos

    def _lista(self, valor: list[Json], esquema: dict[str, Json], ruta: str) -> list[str]:
        fallos: list[str] = []
        cuantos = len(valor)
        minimo, maximo = esquema.get("minItems"), esquema.get("maxItems")
        if minimo is not None and cuantos < minimo:
            fallos.append(f"{ruta}: tiene {cuantos} elementos y el mínimo es {minimo}")
        if maximo is not None and cuantos > maximo:
            fallos.append(f"{ruta}: tiene {cuantos} elementos y el máximo es {maximo}")
        if esquema.get("uniqueItems"):
            vistos: set[str] = set()
            for i, elemento in enumerate(valor):
                forma = _canon(elemento)
                if forma in vistos:
                    fallos.append(f"{ruta}[{i}]: elemento repetido {_json(elemento)}")
                vistos.add(forma)
        if "items" in esquema:
            for i, elemento in enumerate(valor):
                fallos += self.errores(elemento, esquema["items"], f"{ruta}[{i}]")
        return fallos

    @staticmethod
    def _cadena(valor: str, esquema: dict[str, Json], ruta: str) -> list[str]:
        fallos: list[str] = []
        largo = len(valor)
        minimo, maximo = esquema.get("minLength"), esquema.get("maxLength")
        if minimo is not None and largo < minimo:
            fallos.append(f"{ruta}: tiene {largo} caracteres y el mínimo es {minimo}")
        if maximo is not None and largo > maximo:
            fallos.append(f"{ruta}: tiene {largo} caracteres y el máximo es {maximo}")
        patron = esquema.get("pattern")
        if patron is not None and not re.search(patron, valor):
            fallos.append(f"{ruta}: {_json(valor)} no casa con el patrón {patron}")
        if esquema.get("format") == "date" and not _es_fecha(valor):
            fallos.append(f"{ruta}: {_json(valor)} no es una fecha AAAA-MM-DD del calendario")
        return fallos

    @staticmethod
    def _numero(valor: float, esquema: dict[str, Json], ruta: str) -> list[str]:
        fallos: list[str] = []
        if "minimum" in esquema and valor < esquema["minimum"]:
            fallos.append(f"{ruta}: {valor} es menor que el mínimo {esquema['minimum']}")
        if "maximum" in esquema and valor > esquema["maximum"]:
            fallos.append(f"{ruta}: {valor} es mayor que el máximo {esquema['maximum']}")
        if "exclusiveMinimum" in esquema and valor <= esquema["exclusiveMinimum"]:
            fallos.append(f"{ruta}: {valor} no supera el mínimo exclusivo {esquema['exclusiveMinimum']}")
        if "exclusiveMaximum" in esquema and valor >= esquema["exclusiveMaximum"]:
            fallos.append(f"{ruta}: {valor} no baja del máximo exclusivo {esquema['exclusiveMaximum']}")
        return fallos

    def _combinaciones(self, valor: Json, esquema: dict[str, Json], ruta: str) -> list[str]:
        fallos: list[str] = []
        for sub in esquema.get("allOf", []):
            fallos += self.errores(valor, sub, ruta)
        if "anyOf" in esquema and all(self.errores(valor, sub, ruta) for sub in esquema["anyOf"]):
            cuantas = len(esquema["anyOf"])
            fallos.append(f"{ruta}: {_json(valor)} no cumple ninguna de las {cuantas} alternativas (anyOf)")
        if "oneOf" in esquema:
            validas = sum(1 for sub in esquema["oneOf"] if not self.errores(valor, sub, ruta))
            if validas != 1:
                fallos.append(f"{ruta}: cumple {validas} alternativas de oneOf y tiene que cumplir una")
        if "not" in esquema and not self.errores(valor, esquema["not"], ruta):
            fallos.append(f"{ruta}: cumple el esquema prohibido por «not»")
        return fallos


def _es_fecha(texto: str) -> bool:
    """True si es AAAA-MM-DD y existe en el calendario."""
    if not _FECHA_ISO.match(texto):
        return False
    try:
        dt.date.fromisoformat(texto)
    except ValueError:
        return False
    return True


def motor(forzar_minimo: bool) -> str:
    """Describe qué validador se va a usar.

    Args:
        forzar_minimo: True para ignorar ``jsonschema`` aunque esté instalado.

    Returns:
        Una frase para la cabecera de la salida.
    """
    if jsonschema is not None and not forzar_minimo:
        return f"jsonschema {metadata.version('jsonschema')} (Draft 2020-12)"
    motivo = "forzado con --minimo" if jsonschema is not None else "jsonschema no está instalado"
    return f"validador mínimo propio ({motivo})"


def errores_de(valor: Json, esquema: dict[str, Json], forzar_minimo: bool = False) -> list[str]:
    """Valida un documento con el mejor validador disponible.

    Args:
        valor: Documento JSON ya cargado.
        esquema: JSON Schema 2020-12 ya cargado.
        forzar_minimo: True para usar el validador propio aunque ``jsonschema`` esté instalado.

    Returns:
        Mensajes de fallo, ordenados por ruta; lista vacía si el documento es válido.
    """
    if jsonschema is not None and not forzar_minimo:
        clase = jsonschema.Draft202012Validator
        validador = clase(esquema, format_checker=clase.FORMAT_CHECKER)
        return sorted(f"{e.json_path}: {e.message}" for e in validador.iter_errors(valor))
    return ValidadorMinimo(esquema).errores(valor)


# ----------------------------------------------------------------- invariantes entre ficheros


def _leer_json(ruta: Path) -> Json:
    """Carga un JSON en UTF-8."""
    with ruta.open(encoding="utf-8") as fichero:
        return json.load(fichero)


def _csv(ruta: Path) -> list[dict[str, str]]:
    """Lee un CSV del kit (separador ``;``, UTF-8, sin traducir saltos de línea)."""
    with ruta.open(encoding="utf-8", newline="") as fichero:
        return list(csv.DictReader(fichero, delimiter=";"))


def _num(texto: str) -> float:
    """Convierte un importe del CSV (coma decimal, sin separador de millar)."""
    return float(texto.replace(",", "."))


def _fecha_es(iso: str) -> str:
    """``2026-09-07`` → ``07/09/2026``, como en los CSV y en las entradas de los casos."""
    return "/".join(reversed(iso.split("-")))


def _invariantes_pedidos(datos: Path) -> list[str]:
    verdad = _leer_json(datos / "pedidos/pedidos-verdad.json")
    tarifa = {fila["referencia"]: fila for fila in _csv(datos / "pedidos/tarifa.csv")}
    clientes = {fila["cliente"]: fila for fila in _csv(datos / "pedidos/clientes.csv")}
    fallos: list[str] = []
    for pedido in verdad["pedidos"]:
        eti = f"pedidos: {pedido['id']}"
        if not (datos / "pedidos" / pedido["fichero"]).is_file():
            fallos.append(f"{eti}: no existe pedidos/{pedido['fichero']}")
        cliente = clientes.get(pedido["cliente"])
        if cliente is None:
            fallos.append(f"{eti}: el cliente «{pedido['cliente']}» no está en clientes.csv")
        elif (cliente["tarifa"], cliente["nif"]) != (pedido["tarifa"], pedido["nif_cliente"]):
            fallos.append(f"{eti}: la tarifa o el NIF no coinciden con clientes.csv")
        obligatorias = {i["tipo"] for i in pedido["incidencias"] if i["obligatoria"]}
        suma = 0.0
        for linea in pedido["lineas"]:
            ref, precio = linea["referencia"], linea["precio_caja"]
            fila = tarifa.get(ref)
            if precio is None:
                if fila is not None:
                    fallos.append(f"{eti}: {ref} tiene precio null pero está en tarifa.csv")
                if "referencia-inexistente" not in obligatorias:
                    fallos.append(f"{eti}: {ref} no existe y falta la incidencia obligatoria")
                continue
            if fila is None:
                fallos.append(f"{eti}: {ref} no está en tarifa.csv")
                continue
            de_tarifa = _num(fila[f"precio_caja_{pedido['tarifa']}"])
            if abs(de_tarifa - precio) > TOLERANCIA:
                fallos.append(f"{eti}: {ref} vale {precio} y la tarifa {pedido['tarifa']} dice {de_tarifa}")
            suma += linea["cantidad_cajas"] * precio
        if abs(suma - pedido["importe_lineas_eur"]) > TOLERANCIA:
            fallos.append(f"{eti}: importe_lineas_eur {pedido['importe_lineas_eur']} ≠ suma {suma:.2f}")
    return fallos


def _invariantes_correos(datos: Path) -> list[str]:
    verdad = _leer_json(datos / "correos/correos-verdad.json")
    fallos: list[str] = []
    for correo in verdad["correos"]:
        eti = f"correos: {correo['id']}"
        if not (datos / "correos" / correo["fichero"]).is_file():
            fallos.append(f"{eti}: no existe correos/{correo['fichero']}")
        if correo["categoria"] not in verdad["categorias"]:
            fallos.append(f"{eti}: categoría «{correo['categoria']}» fuera de la lista")
        if correo["urgencia"] not in verdad["urgencias"]:
            fallos.append(f"{eti}: urgencia «{correo['urgencia']}» fuera de la lista")
    return fallos


def _invariantes_contrato(datos: Path) -> list[str]:
    verdad = _leer_json(datos / "contrato/contrato-preguntas.json")
    if not (datos / "contrato" / verdad["fichero"]).is_file():
        return [f"contrato: no existe contrato/{verdad['fichero']}"]
    return []


def _invariantes_facturas(datos: Path) -> list[str]:
    verdad = _leer_json(datos / "facturas/facturas-verdad.json")
    registro = {(f["proveedor"], f["numero_factura"]) for f in _csv(datos / "facturas/registro-previo.csv")}
    fallos: list[str] = []
    for factura in verdad["facturas"]:
        eti = f"facturas: {factura['id']}"
        if not (datos / "facturas" / factura["fichero"]).is_file():
            fallos.append(f"{eti}: no existe facturas/{factura['fichero']}")
        total = factura["total"]
        calculado = factura["base"] + factura["iva"] - factura["retencion"] + factura["otros"]
        if abs(calculado - total) > TOLERANCIA:
            fallos.append(f"{eti}: base + iva − retencion + otros da {calculado:.2f} y total dice {total}")
        en_registro = (factura["proveedor"], factura["numero"]) in registro
        if en_registro != factura["duplicada"]:
            fallos.append(f"{eti}: duplicada={factura['duplicada']} y registro-previo.csv dice {en_registro}")
    return fallos


def _invariantes_cobros(datos: Path) -> list[str]:
    verdad = _leer_json(datos / "cobros/cobros-verdad.json")
    cobros = {fila["numero"]: fila for fila in _csv(datos / "cobros/cobros.csv")}
    recordar = {r["factura"]: r for r in verdad["recordar"]}
    numeros = list(recordar) + [r["factura"] for r in verdad["no_recordar"]]
    fallos = [f"cobros: la factura {n} no está en cobros.csv" for n in numeros if n not in cobros]
    for caso in verdad["casos_recordatorio"]:
        eti = f"cobros: {caso['id']}"
        fila = cobros.get(caso["factura"])
        if fila is None:
            fallos.append(f"{eti}: la factura {caso['factura']} no está en cobros.csv")
        else:
            pendiente = _num(fila["importe_total"]) - _num(fila["importe_cobrado"])
            if abs(pendiente - caso["importe_pendiente"]) > TOLERANCIA:
                fallos.append(f"{eti}: importe_pendiente ≠ cobros.csv ({pendiente:.2f})")
            if fila["vencimiento"] != _fecha_es(caso["vencimiento"]):
                fallos.append(f"{eti}: vencimiento distinto del de cobros.csv ({fila['vencimiento']})")
            if int(fila["dias_retraso"]) != caso["dias_retraso"]:
                fallos.append(f"{eti}: dias_retraso distinto del de cobros.csv ({fila['dias_retraso']})")
            if fila["cliente"] != caso["cliente"]:
                fallos.append(f"{eti}: cliente distinto del de cobros.csv ({fila['cliente']})")
        origen = recordar.get(caso["factura"])
        if origen is None:
            fallos.append(f"{eti}: la factura {caso['factura']} no está en «recordar»")
        else:
            campos = (
                "cliente",
                "contacto",
                "importe_pendiente",
                "vencimiento",
                "dias_retraso",
                "tono",
            )
            fallos += [
                f"{eti}: {campo} distinto del de «recordar» ({origen[campo]})"
                for campo in campos
                if origen[campo] != caso[campo]
            ]
        tono = verdad["tonos"].get(caso["tono"], {})
        reglas = caso["reglas"]
        if reglas["no_debe_contener"] != tono.get("prohibido"):
            fallos.append(f"{eti}: no_debe_contener no es el «prohibido» del tono {caso['tono']}")
        if reglas["debe_contener_expresion"] != tono.get("obligatorio"):
            fallos.append(f"{eti}: debe_contener_expresion no es el «obligatorio» del tono {caso['tono']}")
        if reglas["debe_nombrar_cliente"] != caso["contacto"].split()[0]:
            fallos.append(f"{eti}: debe_nombrar_cliente no es el nombre de pila de {caso['contacto']}")
        grupos = reglas["debe_contener_alguno"]
        importe = f"{caso['importe_pendiente']:.2f}".replace(".", ",")
        esperado = (caso["factura"], importe, _fecha_es(caso["vencimiento"]))
        for i, (grupo, valor) in enumerate(zip(grupos, esperado, strict=False)):
            if valor not in grupo:
                fallos.append(f"{eti}: el grupo {i} de debe_contener_alguno no incluye «{valor}»")
    return fallos


def invariantes(datos: Path) -> list[str]:
    """Comprueba lo que los esquemas no pueden decir: coherencia entre ficheros.

    Args:
        datos: Carpeta ``datos/``.

    Returns:
        Mensajes de fallo; lista vacía si todo cuadra.
    """
    fallos: list[str] = []
    for comprobar in (
        _invariantes_pedidos,
        _invariantes_correos,
        _invariantes_contrato,
        _invariantes_facturas,
        _invariantes_cobros,
    ):
        fallos += comprobar(datos)
    return fallos


# ----------------------------------------------------------------- línea de órdenes


def _salida_utf8() -> None:
    """Escribe en UTF-8 aunque la consola esté en otra codificación (Windows)."""
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")


def _cargar(ruta: Path) -> Json:
    """Carga un JSON o termina con código 2 explicando qué no se pudo leer."""
    try:
        return _leer_json(ruta)
    except (OSError, ValueError) as error:
        print(f"No se puede leer {ruta}: {error}", file=sys.stderr)
        sys.exit(2)


def _validar_uno(fichero: Path, esquema: Path, forzar_minimo: bool) -> int:
    """Valida un JSON cualquiera contra un esquema cualquiera y lo cuenta."""
    fallos = errores_de(_cargar(fichero), _cargar(esquema), forzar_minimo)
    if not fallos:
        print(f"VÁLIDO    {fichero} contra {esquema.name}")
        return 0
    print(f"INVÁLIDO  {fichero} contra {esquema.name}: {len(fallos)} fallos")
    for fallo in fallos:
        print(f"    {fallo}")
    return 1


def _comprobar_esquemas_respuesta(datos: Path) -> int:
    """Comprueba que los cinco esquemas de respuesta cargan y son objetos del draft 2020-12."""
    problemas = 0
    for tarea in TAREAS:
        ruta = datos / "esquemas" / f"respuesta-{tarea}.schema.json"
        esquema = _cargar(ruta)
        raros = [k for k in ("$schema", "type", "required", "properties") if k not in esquema]
        if esquema.get("$schema") != DRAFT or esquema.get("type") != "object" or raros:
            print(f"ESQUEMA   esquemas/{ruta.name}: no es un esquema de objeto 2020-12 ({raros})")
            problemas += 1
            continue
        print(f"ESQUEMA   esquemas/{ruta.name}: claves requeridas {', '.join(esquema['required'])}")
    return problemas


def _validar_todo(datos: Path, forzar_minimo: bool, con_invariantes: bool) -> int:
    """Valida los cinco ficheros de verdad, los esquemas de respuesta y las invariantes."""
    problemas = 0
    for fichero, esquema, clave in PAREJAS:
        documento = _cargar(datos / fichero)
        fallos = errores_de(documento, _cargar(datos / esquema), forzar_minimo)
        casos = len(documento.get(clave, [])) if isinstance(documento, dict) else 0
        if fallos:
            problemas += 1
            print(f"INVÁLIDO  {fichero} contra {Path(esquema).name}: {len(fallos)} fallos")
            for fallo in fallos:
                print(f"    {fallo}")
        else:
            print(f"VÁLIDO    {fichero} ({casos} {clave}) contra {Path(esquema).name}")
    problemas += _comprobar_esquemas_respuesta(datos)
    if con_invariantes:
        fallos = invariantes(datos)
        if fallos:
            problemas += 1
            print(f"INVÁLIDO  invariantes entre ficheros: {len(fallos)} fallos")
            for fallo in fallos:
                print(f"    {fallo}")
        else:
            print("VÁLIDO    invariantes entre ficheros (tarifa, clientes, registro previo, cobros)")
    if problemas:
        print(f"{problemas} comprobaciones con fallos.", file=sys.stderr)
        return 1
    print("Todo válido.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada de la línea de órdenes.

    Args:
        argv: Argumentos sin el nombre del programa; ``None`` para usar ``sys.argv``.

    Returns:
        0 válido, 1 inválido, 2 no se pudo leer algo.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Valida los ficheros de verdad del kit contra sus JSON Schema, "
            "o un JSON cualquiera contra un esquema cualquiera."
        ),
    )
    parser.add_argument("fichero", nargs="?", type=Path, help="JSON a validar (va con ESQUEMA)")
    parser.add_argument("esquema", nargs="?", type=Path, help="JSON Schema 2020-12 contra el que validar")
    parser.add_argument(
        "--datos",
        type=Path,
        default=DATOS_POR_DEFECTO,
        help=f"carpeta de datos (por defecto {DATOS_POR_DEFECTO})",
    )
    parser.add_argument(
        "--minimo",
        action="store_true",
        help="usa el validador propio aunque jsonschema esté instalado",
    )
    parser.add_argument(
        "--sin-invariantes",
        action="store_true",
        help="no comprueba la coherencia entre ficheros (solo esquemas)",
    )
    args = parser.parse_args(argv)
    _salida_utf8()
    if (args.fichero is None) != (args.esquema is None):
        parser.error("FICHERO y ESQUEMA van juntos")
    print(f"Motor: {motor(args.minimo)}")
    if args.fichero is not None:
        return _validar_uno(args.fichero, args.esquema, args.minimo)
    if not args.datos.is_dir():
        print(f"No existe la carpeta de datos: {args.datos}", file=sys.stderr)
        return 2
    return _validar_todo(args.datos, args.minimo, not args.sin_invariantes)


if __name__ == "__main__":
    sys.exit(main())
