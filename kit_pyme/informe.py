"""El resultado de una prueba con la forma exacta de ``ResultadoPrueba`` del blog, y su tabla.

``resultado.json`` lleva las claves en el orden en que las construye ``src/pruebas/index.ts``
(líneas 332-346): ``novedad_url, modelo, tarea, tarea_nombre, casos, aciertos, fallos,
segundos, coste_eur, veredicto, nota`` y, solo si son mayores que cero, ``sin_respuesta``
y ``errores_servicio``. ``detalle.json`` guarda además cada caso (respuesta, esperado,
segundos, uso, error), como el registro que el blog deja en R2.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kit_pyme import javascript as js
from kit_pyme.cliente import Uso
from kit_pyme.esquema import normalizar_claves, validar_contra_esquema
from kit_pyme.puntuacion import (
    AUSENTE,
    nota_por_reglas,
    puntuar,
    puntuar_caso,
    veredicto_por_reglas,
)
from kit_pyme.tareas import Caso, Tarea


@dataclass
class Registro:
    """Lo que queda de cada caso tras probarlo.

    Attributes:
        id: Identificador del caso.
        ok: Si acertó.
        fallo: La frase del fallo, si lo hubo.
        respuesta: El JSON que se puntuó (``AUSENTE`` si no hubo respuesta válida).
        texto_modelo: El texto tal cual del modelo.
        esperado: La respuesta correcta.
        segundos: Lo que tardó el caso.
        uso: Tokens y coste del caso, intentos perdidos incluidos.
        error: Mensaje del error, si la llamada no devolvió nada válido.
        error_estado: Código HTTP del error, si lo hubo.
        error_servicio: Si el error fue del servicio (red, 429, 5xx, o caso saltado).
    """

    id: str
    ok: bool
    respuesta: Any
    esperado: Any
    fallo: str | None = None
    texto_modelo: str | None = None
    segundos: float = 0.0
    uso: Uso | None = None
    error: str | None = None
    error_estado: int | None = None
    error_servicio: bool = False

    def como_dict(self) -> dict[str, Any]:
        """El registro como diccionario serializable, con las claves del blog.

        Returns:
            El diccionario.
        """
        d: dict[str, Any] = {"id": self.id, "ok": self.ok}
        if self.fallo is not None:
            d["fallo"] = self.fallo
        d["respuesta"] = None if self.respuesta is AUSENTE else self.respuesta
        if self.texto_modelo is not None:
            d["texto_modelo"] = self.texto_modelo
        d["esperado"] = self.esperado
        d["segundos"] = self.segundos
        if self.uso is not None:
            d["uso"] = self.uso.como_dict()
        if self.error is not None:
            d["error"] = self.error
        if self.error_estado is not None:
            d["error_estado"] = self.error_estado
        return d


@dataclass
class Informe:
    """Resultado y detalle de una tarea probada.

    Attributes:
        resultado: El ``ResultadoPrueba``, listo para ``resultado.json``.
        registros: Un registro por caso.
        uso: Suma de tokens y coste de todos los casos.
        todos_los_fallos: Todos los fallos, en orden de caso.
    """

    resultado: dict[str, Any]
    registros: list[Registro]
    uso: Uso
    todos_los_fallos: list[str] = field(default_factory=list)

    def detalle(self, modelo_pedido: str | None = None) -> dict[str, Any]:
        """El detalle completo, con la forma del registro que el blog guarda en R2.

        Args:
            modelo_pedido: El id de modelo que se pidió (por si la API devolvió otro nombre).

        Returns:
            El diccionario para ``detalle.json``.
        """
        return {
            "modelo": self.resultado["modelo"],
            "modelo_pedido": modelo_pedido or self.resultado["modelo"],
            "tarea": self.resultado["tarea"],
            "realizada": True,
            "modo_barato": "(muestra de" in self.resultado["tarea_nombre"],
            "resultado": self.resultado,
            "uso": self.uso.como_dict(),
            "todos_los_fallos": self.todos_los_fallos,
            "casos": [r.como_dict() for r in self.registros],
        }


def construir_informe(
    tarea: Tarea,
    casos: list[Caso],
    registros: list[Registro],
    segundos: float,
    modelo: str,
    novedad_url: str = "",
    modo_barato: bool = False,
) -> Informe:
    """Puntúa los registros y construye el ``ResultadoPrueba`` como lo hace el blog.

    Args:
        tarea: La tarea probada.
        casos: Los casos probados, en orden.
        registros: Un registro por caso, en el mismo orden (con la respuesta ya normalizada).
        segundos: Tiempo de pared del lote, ya redondeado a una décima.
        modelo: Id del modelo probado.
        novedad_url: URL de la novedad que se prueba (vacía en el kit).
        modo_barato: Si se ha recortado la lista de casos.

    Returns:
        El informe.
    """
    puntuacion = puntuar(tarea.id, casos, [r.respuesta for r in registros])
    for r, caso in zip(registros, casos, strict=True):
        res = puntuar_caso(tarea.id, caso, r.respuesta)
        r.ok = res.ok
        r.fallo = res.fallo
    uso = Uso()
    for r in registros:
        if r.uso is not None:
            uso = uso + r.uso
    coste_eur = js.redondear(uso.coste_eur * 10000) / 10000
    errores_servicio = sum(1 for r in registros if r.error and r.error_servicio)
    sin_respuesta = sum(1 for r in registros if r.error or r.respuesta is AUSENTE or r.respuesta is None)
    veredicto = veredicto_por_reglas(puntuacion.aciertos, len(casos), coste_eur, sin_respuesta)
    resultado: dict[str, Any] = {
        "novedad_url": novedad_url,
        "modelo": modelo,
        "tarea": tarea.id,
        "tarea_nombre": f"{tarea.nombre} (muestra de {len(casos)} casos)" if modo_barato else tarea.nombre,
        "casos": len(casos),
        "aciertos": puntuacion.aciertos,
        "fallos": puntuacion.fallos,
        "segundos": segundos,
        "coste_eur": coste_eur,
        "veredicto": veredicto,
        "nota": nota_por_reglas(
            veredicto,
            puntuacion.aciertos,
            len(casos),
            coste_eur,
            puntuacion.fallos,
            sin_respuesta,
            errores_servicio,
        ),
    }
    if sin_respuesta:
        resultado["sin_respuesta"] = sin_respuesta
    if errores_servicio:
        resultado["errores_servicio"] = errores_servicio
    return Informe(
        resultado=resultado,
        registros=registros,
        uso=uso,
        todos_los_fallos=puntuacion.todos_los_fallos,
    )


def leer_jsonl(ruta: Path) -> list[dict[str, Any]]:
    """Lee un fichero con un objeto JSON por línea (las líneas en blanco se ignoran).

    Se lee como ``utf-8-sig``: el fichero de respuestas lo escribe quien prueba la
    herramienta, y en Windows el Bloc de notas y ``Out-File`` le ponen una marca de orden
    de bytes que no es JSON. Un fichero UTF-8 normal se lee igual.

    Args:
        ruta: Ruta del fichero.

    Returns:
        La lista de objetos.

    Raises:
        ValueError: Si una línea no es un objeto JSON.
    """
    filas: list[dict[str, Any]] = []
    with open(ruta, encoding="utf-8-sig") as f:
        for n, linea in enumerate(f, start=1):
            if not linea.strip():
                continue
            try:
                fila = json.loads(linea)
            except ValueError as e:
                raise ValueError(f"{ruta}:{n}: no es JSON ({e})") from e
            if not isinstance(fila, dict):
                raise ValueError(f"{ruta}:{n}: cada línea tiene que ser un objeto {{id, respuesta}}")
            filas.append(fila)
    return filas


def registros_desde_jsonl(tarea: Tarea, casos: list[Caso], filas: list[dict[str, Any]]) -> list[Registro]:
    """Convierte respuestas dadas en registros, pasando por el mismo filtro que el blog.

    A cada respuesta objeto se le aplican ``normalizar_claves`` y ``validar_contra_esquema``;
    si no cumple el esquema, cuenta como sin respuesta (en el blog una respuesta así nunca
    llega a puntuarse). Un caso sin línea también cuenta como sin respuesta; una línea con
    ``respuesta: null`` llega al comparador como ``null``.

    Args:
        tarea: La tarea.
        casos: Los casos, en orden.
        filas: Las líneas del jsonl, ``{"id", "respuesta"}`` y opcionalmente ``uso`` y ``segundos``.

    Returns:
        Un registro por caso.
    """
    por_id = {str(f.get("id")): f for f in filas}
    registros: list[Registro] = []
    for caso in casos:
        fila = por_id.get(caso.id)
        if fila is None:
            registros.append(
                Registro(
                    id=caso.id,
                    ok=False,
                    respuesta=AUSENTE,
                    esperado=caso.esperado,
                    error="sin línea en el jsonl",
                )
            )
            continue
        respuesta = fila.get("respuesta")
        uso = None
        if isinstance(fila.get("uso"), dict):
            u = fila["uso"]
            uso = Uso(
                int(u.get("tokens_entrada") or 0),
                int(u.get("tokens_salida") or 0),
                float(u.get("coste_eur") or 0),
            )
        segundos = float(fila.get("segundos") or 0)
        error = None
        if respuesta is not None:
            respuesta = normalizar_claves(respuesta, tarea.esquema)
            fallos = validar_contra_esquema(respuesta, tarea.esquema)
            if fallos:
                error = f"JSON no cumple el esquema: {', '.join(fallos)}"
                respuesta = AUSENTE
        registros.append(
            Registro(
                id=caso.id,
                ok=False,
                respuesta=respuesta,
                esperado=caso.esperado,
                segundos=segundos,
                uso=uso,
                error=error,
            )
        )
    return registros


def tabla(resultado: dict[str, Any]) -> str:
    """Una tabla legible del resultado, para la consola.

    Args:
        resultado: El ``ResultadoPrueba``.

    Returns:
        Texto de varias líneas.
    """
    filas = [
        ("Tarea", f"{resultado['tarea']} — {resultado['tarea_nombre']}"),
        ("Modelo", resultado["modelo"] or "(sin modelo)"),
        ("Casos", str(resultado["casos"])),
        ("Aciertos", f"{resultado['aciertos']} de {resultado['casos']}"),
        ("Segundos", js.texto_de_numero(resultado["segundos"])),
        ("Coste", f"{js.texto_de_numero(resultado['coste_eur'])} €"),
        ("Veredicto", resultado["veredicto"]),
        ("Nota", resultado["nota"]),
    ]
    if resultado.get("sin_respuesta"):
        filas.append(("Sin respuesta", str(resultado["sin_respuesta"])))
    if resultado.get("errores_servicio"):
        filas.append(("Errores del servicio", str(resultado["errores_servicio"])))
    ancho = max(len(k) for k, _ in filas)
    lineas = [f"{k.ljust(ancho)}  {v}" for k, v in filas]
    if resultado["fallos"]:
        lineas.append("Fallos publicados (hasta 3):")
        lineas.extend(f"  - {f}" for f in resultado["fallos"])
    return "\n".join(lineas)


def escribir_json(ruta: Path, valor: Any) -> None:
    """Escribe un JSON con sangría de dos espacios, UTF-8 y LF.

    Args:
        ruta: Ruta de destino (se crean las carpetas que falten).
        valor: El valor a escribir.
    """
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8", newline="\n") as f:
        json.dump(valor, f, ensure_ascii=False, indent=2)
        f.write("\n")
