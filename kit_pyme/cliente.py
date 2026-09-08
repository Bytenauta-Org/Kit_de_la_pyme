"""Llamada a un modelo por un endpoint compatible con OpenAI, solo con ``urllib``.

Es la traducción de ``llamarModelo`` de ``src/pruebas/index.ts`` en modo directo (el de
producción del blog y el de las cifras publicadas): mensaje de sistema y de usuario,
``max_tokens`` de la tarea, ``temperature: 0`` salvo en los modelos que la rechazan (se
aprende del primer 400 que se queja de ella y no se repite el viaje), sin
``response_format`` (el prompt pide JSON y ``esquema.extraer_json`` lo saca), tres
intentos con espera creciente para errores de red, 429 y 5xx, y los 4xx restantes
lanzados al momento (el modelo no existe o no está autorizado).

El coste se estima con la tabla de ``precios.json`` (euros por millón de tokens) sobre los
tokens que declara la respuesta, y los intentos descartados se suman al bueno, como en el
blog.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kit_pyme.esquema import extraer_json, normalizar_claves, validar_contra_esquema

#: Endpoints compatibles con OpenAI de los proveedores que el blog llama en directo.
ENDPOINTS_DIRECTOS: dict[str, str] = {
    "anthropic": "https://api.anthropic.com/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
}

#: Tabla de precios que se usa si no se pasa otra.
RUTA_PRECIOS = Path(__file__).with_name("precios.json")

_TEMPERATURA_RE = re.compile("temperature", re.IGNORECASE)
_OBSOLETA_RE = re.compile("deprecat|not supported|unsupported", re.IGNORECASE)
_CLAUDE_RE = re.compile("claude", re.IGNORECASE)
_GPT_RE = re.compile(r"gpt|o\d", re.IGNORECASE)
_GEMINI_RE = re.compile("gemini", re.IGNORECASE)


@dataclass
class Uso:
    """Tokens y coste de una llamada (o de una tarea entera).

    Attributes:
        tokens_entrada: Tokens del prompt.
        tokens_salida: Tokens de la respuesta.
        coste_eur: Coste estimado en euros.
    """

    tokens_entrada: int = 0
    tokens_salida: int = 0
    coste_eur: float = 0.0

    def __add__(self, otro: Uso) -> Uso:
        """Suma dos usos campo a campo.

        Args:
            otro: El otro uso.

        Returns:
            Un uso nuevo con las sumas.
        """
        return Uso(
            self.tokens_entrada + otro.tokens_entrada,
            self.tokens_salida + otro.tokens_salida,
            self.coste_eur + otro.coste_eur,
        )

    def como_dict(self) -> dict[str, Any]:
        """El uso como diccionario, con las claves del blog.

        Returns:
            ``{"tokens_entrada", "tokens_salida", "coste_eur"}``.
        """
        return {
            "tokens_entrada": self.tokens_entrada,
            "tokens_salida": self.tokens_salida,
            "coste_eur": self.coste_eur,
        }


@dataclass
class RespuestaModelo:
    """Lo que devuelve una llamada que ha salido bien.

    Attributes:
        datos: El JSON de la respuesta, ya con las claves normalizadas y validado.
        texto: El texto tal cual lo devolvió el modelo.
        uso: Tokens y coste, incluidos los intentos descartados.
        modelo: El nombre de modelo que devolvió la API.
    """

    datos: Any
    texto: str
    uso: Uso
    modelo: str


class ErrorCliente(Exception):
    """Una llamada al modelo que no ha devuelto una respuesta válida.

    Attributes:
        estado: Código HTTP, si lo hubo.
        cuerpo: Principio del cuerpo de la respuesta, si lo hubo.
        red: Si fue un error de red (sin respuesta del servicio).
        uso: Lo que costaron los intentos, aunque no sirvieran.
    """

    def __init__(
        self,
        mensaje: str,
        estado: int | None = None,
        cuerpo: str | None = None,
        red: bool = False,
        uso: Uso | None = None,
    ) -> None:
        """Construye el error.

        Args:
            mensaje: Explicación en una frase.
            estado: Código HTTP, si lo hubo.
            cuerpo: Principio del cuerpo de la respuesta, si lo hubo.
            red: Si fue un error de red.
            uso: Lo que costaron los intentos.
        """
        super().__init__(mensaje)
        self.estado = estado
        self.cuerpo = cuerpo
        self.red = red
        self.uso = uso or Uso()

    @property
    def es_del_servicio(self) -> bool:
        """Si el servicio no contestó (red, 429 o 5xx), frente a contestar algo ilegible."""
        if self.estado is not None:
            return self.estado >= 500 or self.estado == 429
        return self.red

    @property
    def no_disponible(self) -> bool:
        """Si es un 4xx distinto de 429: el modelo no existe o no está autorizado."""
        return self.estado is not None and 400 <= self.estado < 500 and self.estado != 429


@dataclass
class Peticion:
    """Lo que se le pide al modelo en una llamada.

    Attributes:
        system: Mensaje de sistema (el prompt de la tarea con la línea FORMATO).
        user: Mensaje de usuario (la entrada del caso).
        esquema: JSON Schema de la respuesta; si se da, se exige JSON y se valida.
        max_tokens: Tope de tokens de salida.
        temperatura: Temperatura; el blog usa 0 en el banco.
    """

    system: str
    user: str
    esquema: dict[str, Any] | None = None
    max_tokens: int = 1500
    temperatura: float = 0.0


@dataclass
class Cliente:
    """Un endpoint compatible con OpenAI y todo lo que hace falta para llamarlo.

    Attributes:
        endpoint: URL de ``chat/completions``.
        clave: Clave de API (va como ``Authorization: Bearer``); vacía si no hace falta.
        precios: Tabla de precios por modelo (euros por millón de tokens).
        reintentos: Intentos adicionales tras el primero (2 en el blog).
        tiempo_maximo: Segundos de espera por respuesta.
        dormir: Función de espera (se sustituye en los tests).
        sin_temperatura: Modelos que han rechazado ``temperature``; se aprende sobre la marcha.
    """

    endpoint: str
    clave: str = ""
    precios: dict[str, Any] = field(default_factory=dict)
    reintentos: int = 2
    tiempo_maximo: float = 300.0
    dormir: Callable[[float], None] = time.sleep
    sin_temperatura: set[str] = field(default_factory=set)

    def llamar(self, modelo: str, modelo_api: str, p: Peticion) -> RespuestaModelo:
        """Llama al modelo y devuelve el JSON validado, con reintentos como los del blog.

        Args:
            modelo: Id con el que se etiqueta y se cobra («anthropic/claude-haiku-4-5»).
            modelo_api: Nombre que se envía en ``model`` («claude-haiku-4-5»).
            p: La petición.

        Returns:
            La respuesta con datos, texto, uso y modelo real.

        Raises:
            ErrorCliente: Si se agotan los intentos o el endpoint devuelve un 4xx.
        """
        cuerpo: dict[str, Any] = {
            "model": modelo_api,
            "messages": [
                {"role": "system", "content": p.system},
                {"role": "user", "content": p.user},
            ],
            "max_tokens": p.max_tokens,
        }
        if modelo not in self.sin_temperatura:
            cuerpo["temperature"] = p.temperatura
        cabeceras = {"content-type": "application/json"}
        if self.clave:
            cabeceras["authorization"] = f"Bearer {self.clave}"
        ultimo_error: ErrorCliente | None = None
        uso_perdido = Uso()
        intento = 0
        while intento <= self.reintentos:
            intento += 1
            estado, texto = self._enviar(cuerpo, cabeceras)
            if estado is None:
                ultimo_error = ErrorCliente(f"Sin respuesta del servicio: {texto}", red=True)
                self.dormir(0.5 * intento)
                continue
            if not 200 <= estado < 300:
                ultimo_error = ErrorCliente(f"El endpoint respondió {estado} con {modelo}", estado, texto[:500])
                if es_temperatura_obsoleta(estado, texto) and modelo not in self.sin_temperatura:
                    self.sin_temperatura.add(modelo)
                    cuerpo.pop("temperature", None)
                    intento -= 1
                    continue
                if 400 <= estado < 500 and estado != 429:
                    raise ultimo_error
                self.dormir(0.8 * intento)
                continue
            try:
                respuesta = json.loads(texto)
            except ValueError:
                ultimo_error = ErrorCliente("La respuesta del endpoint no es JSON", estado, texto[:300])
                continue
            contenido = _contenido(respuesta)
            if not contenido:
                ultimo_error = ErrorCliente("Respuesta vacía del modelo", estado, texto[:300])
                continue
            modelo_real = respuesta.get("model") if isinstance(respuesta, dict) else None
            if modelo_real is None:
                modelo_real = modelo
            uso_api = respuesta.get("usage") or {} if isinstance(respuesta, dict) else {}
            tokens_entrada = int(uso_api.get("prompt_tokens") or 0)
            tokens_salida = int(uso_api.get("completion_tokens") or 0)
            coste = estimar_coste(
                normalizar_modelo(str(modelo_real), modelo),
                tokens_entrada,
                tokens_salida,
                self.precios,
            )
            uso = Uso(tokens_entrada, tokens_salida, coste)
            if p.esquema is None:
                return RespuestaModelo({"texto": contenido}, contenido, uso + uso_perdido, str(modelo_real))
            try:
                datos = normalizar_claves(extraer_json(contenido), p.esquema)
            except ValueError as e:
                uso_perdido = uso + uso_perdido
                ultimo_error = ErrorCliente(f"JSON inválido ({e})")
                continue
            fallos = validar_contra_esquema(datos, p.esquema)
            if fallos:
                uso_perdido = uso + uso_perdido
                ultimo_error = ErrorCliente(f"JSON no cumple el esquema: {', '.join(fallos)}")
                continue
            return RespuestaModelo(datos, contenido, uso + uso_perdido, str(modelo_real))
        fallo = ultimo_error or ErrorCliente("Fallo desconocido llamando al modelo")
        fallo.uso = uso_perdido
        raise fallo

    def _enviar(self, cuerpo: dict[str, Any], cabeceras: dict[str, str]) -> tuple[int | None, str]:
        """Hace el POST. Devuelve ``(estado, texto)``; ``(None, motivo)`` si no hubo respuesta."""
        datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        peticion = urllib.request.Request(self.endpoint, data=datos, headers=cabeceras, method="POST")
        try:
            with urllib.request.urlopen(peticion, timeout=self.tiempo_maximo) as resp:
                return int(resp.status), resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return int(e.code), e.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            return None, str(getattr(e, "reason", e))


def _contenido(respuesta: Any) -> str:
    """``choices[0].message.content`` como texto (cadena o lista de partes con ``text``)."""
    if not isinstance(respuesta, dict):
        return ""
    choices = respuesta.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""
    mensaje = choices[0].get("message")
    if not isinstance(mensaje, dict):
        return ""
    bruto = mensaje.get("content")
    if isinstance(bruto, str):
        return bruto
    if isinstance(bruto, list):
        return "".join(str((b or {}).get("text") or "") for b in bruto if isinstance(b, dict))
    return ""


def es_temperatura_obsoleta(estado: int | None, cuerpo: str | None) -> bool:
    """Un 400 que solo se queja de ``temperature``: se puede reintentar sin ella.

    Args:
        estado: Código HTTP.
        cuerpo: Cuerpo de la respuesta.

    Returns:
        Si es ese 400.
    """
    c = cuerpo or ""
    return estado == 400 and bool(_TEMPERATURA_RE.search(c)) and bool(_OBSOLETA_RE.search(c))


def cargar_precios(ruta: Path | None = None) -> dict[str, Any]:
    """Carga la tabla de precios (por defecto la del paquete).

    Args:
        ruta: Fichero JSON con la tabla; ``None`` para la del paquete.

    Returns:
        La tabla, sin las claves que empiezan por ``_``.
    """
    with open(ruta or RUTA_PRECIOS, encoding="utf-8") as f:
        tabla = json.load(f)
    return {k: v for k, v in tabla.items() if not k.startswith("_")}


def estimar_coste(modelo: str, tokens_entrada: int, tokens_salida: int, precios: dict[str, Any]) -> float:
    """Coste en euros según la tabla; un modelo que no esté se cobra a ``por_defecto``.

    Args:
        modelo: Id normalizado del modelo («anthropic/claude-haiku-4-5»).
        tokens_entrada: Tokens del prompt.
        tokens_salida: Tokens de la respuesta.
        precios: Tabla de precios (euros por millón de tokens).

    Returns:
        El coste, sin redondear.
    """
    p = precios.get(modelo)
    if p is None:
        p = precios["por_defecto"]
    return (tokens_entrada * p["entrada"] + tokens_salida * p["salida"]) / 1_000_000


def normalizar_modelo(modelo: str, principal: str) -> str:
    """Pone el prefijo de proveedor al nombre que devuelve la API, para la tabla de precios.

    Args:
        modelo: Nombre devuelto por la API («claude-haiku-4-5-20251001»).
        principal: Id que se pidió, por si el nombre no dice de quién es.

    Returns:
        «proveedor/modelo».
    """
    if "/" in modelo:
        return modelo
    if _CLAUDE_RE.search(modelo):
        return f"anthropic/{modelo}"
    if _GPT_RE.search(modelo):
        return f"openai/{modelo}"
    if _GEMINI_RE.search(modelo):
        return f"google/{modelo}"
    return principal


def partir_modelo(modelo: str) -> tuple[str, str]:
    """«anthropic/claude-opus-5» → («anthropic», «claude-opus-5»); sin barra, es de Anthropic.

    Args:
        modelo: Id del modelo.

    Returns:
        Proveedor y nombre.
    """
    if "/" not in modelo:
        return "anthropic", modelo
    proveedor, nombre = modelo.split("/", 1)
    return ("google" if proveedor == "google-ai-studio" else proveedor), nombre


def endpoint_directo(modelo: str) -> str | None:
    """El endpoint compatible con OpenAI del proveedor del modelo, si lo conocemos.

    Args:
        modelo: Id del modelo.

    Returns:
        La URL, o ``None`` si el proveedor no está en la tabla.
    """
    proveedor, _ = partir_modelo(modelo)
    return ENDPOINTS_DIRECTOS.get(proveedor)
