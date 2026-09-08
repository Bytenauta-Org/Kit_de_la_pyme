"""La puntuación: una función por tarea, el veredicto y la nota.

Traducción regla por regla de ``src/pruebas/puntuar.ts`` (comparadores) y de
``veredictoPorReglas``/``notaPorReglas`` de ``src/pruebas/index.ts`` del blog. Es
determinista: reglas, no otra IA que juzga. Cada comparador devuelve si el caso está bien
y, si no, la misma frase que publicaría el blog («Pedido 07: leyó 12 cajas donde ponía
120»). El orden de las comprobaciones importa: el primer fallo corta.

``tests/oro/fallos-negativos.json`` tiene 112 respuestas trucadas con el ``ok`` y el texto
de fallo exactos que devuelve el TypeScript; el Python tiene que devolver los mismos.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Final

from kit_pyme import javascript as js
from kit_pyme.normalizar import (
    etiqueta,
    formatear_euros,
    leer_booleano,
    leer_fecha,
    leer_numero,
    lista,
    normalizar_referencia,
    normalizar_texto,
    objeto,
    texto,
)
from kit_pyme.tareas import Caso, fecha_es


class _Ausente:
    """El valor «no hubo respuesta» (``undefined`` en el blog), distinto de ``None`` (``null``)."""

    def __repr__(self) -> str:
        return "AUSENTE"


#: Marca de «el modelo no devolvió una respuesta válida» (la llamada agotó los reintentos).
AUSENTE: Final = _Ausente()

#: Umbrales del veredicto. Son reglas, no opiniones (``index.ts:44-48``).
UMBRALES: Final[dict[str, float]] = {
    "aciertos_lunes": 0.9,
    "aciertos_humo": 0.6,
    "coste_caso_lunes_eur": 0.05,
}

#: Palabras que no identifican a un cliente por sí solas («Distribuciones S.L.» no es nadie).
GENERICOS_CLIENTE: Final[frozenset[str]] = frozenset(
    {
        "supermercados",
        "distribuciones",
        "restaurante",
        "bar",
        "cafeteria",
        "bar-cafeteria",
        "cooperativa",
        "agricola",
        "grupo",
        "hostelero",
        "catering",
        "ultramarinos",
        "cash",
        "online",
        "eventos",
        "hijos",
        "hermanos",
        "coop",
        "ltd",
        "sl",
        "slu",
        "sa",
        "v",
    }
)

_REFERENCIA_INCIDENCIA_RE = re.compile(r"CONS-[A-Z0-9-]+")
_PISTA_INEXISTENTE_RE = re.compile("no existe|inexistente|desconocid|no esta en|no figura|no encontr")
_PISTA_PRECIO_RE = re.compile("precio|tarifa|distint|difer|discrep")
_PUNTUACION_CLIENTE_RE = re.compile(r"[().,]")
_CATEGORIA_SEPARADOR_RE = re.compile("[" + js.CLASE_ESPACIOS[1:-1] + "_]+")
_TOKEN_CLAUSULA_RE = re.compile("[^0-9a-z.]+")
_LETRA_RE = re.compile("[a-z]")
_PALABRAS_RE = re.compile(js.CLASE_ESPACIOS + "+")


@dataclass(frozen=True)
class ResultadoCaso:
    """Resultado de puntuar un caso.

    Attributes:
        ok: Si el caso está bien.
        fallo: Si no, la frase que lo explica.
    """

    ok: bool
    fallo: str | None = None


@dataclass(frozen=True)
class Puntuacion:
    """Resultado de puntuar una tarea entera.

    Attributes:
        aciertos: Casos bien.
        fallos: Hasta tres fallos descritos en una frase (los que publica el blog).
        todos_los_fallos: Todos los fallos, en orden de caso.
    """

    aciertos: int
    fallos: list[str]
    todos_los_fallos: list[str]


def _bien() -> ResultadoCaso:
    return ResultadoCaso(ok=True)


def _mal(fallo: str) -> ResultadoCaso:
    return ResultadoCaso(ok=False, fallo=fallo)


# ===== extraer-pedidos =====


def cliente_coincide(esperado: str, obtenido: Any) -> bool:
    """Si el cliente obtenido nombra al esperado con alguna palabra que lo identifique.

    Se parte el nombre esperado en palabras de cuatro o más letras que no sean genéricas
    («supermercados», «hermanos», «sl»…) y basta con que una aparezca en lo obtenido:
    «Hnos. Cascales» identifica a «Distribuciones Hermanos Cascales S.L.».

    Args:
        esperado: Nombre del cliente en ``clientes.csv``.
        obtenido: Lo que ha dicho el modelo.

    Returns:
        Si coincide.
    """
    o = normalizar_texto(obtenido)
    if not o:
        return False
    palabras = [
        p
        for p in _PUNTUACION_CLIENTE_RE.sub(" ", normalizar_texto(esperado)).split(" ")
        if len(p) >= 4 and p not in GENERICOS_CLIENTE
    ]
    return any(p in o for p in palabras)


def _coalescer(o: dict[str, Any], primera: str, segunda: str) -> Any:
    """``o[primera] ?? o[segunda]``: la segunda solo si la primera falta o es ``None``."""
    v = o.get(primera)
    return v if v is not None else o.get(segunda)


def puntuar_pedido(caso: Caso, respuesta: Any) -> ResultadoCaso:
    """Puntúa un pedido: cada línea esperada con su referencia, cantidad y precio de tarifa.

    En este orden: líneas que faltan, cantidades mal, precios que no son de tarifa (±0,011 €),
    líneas inventadas, líneas duplicadas, incidencias obligatorias y cliente.

    Args:
        caso: El caso, con el pedido esperado.
        respuesta: Lo que ha devuelto el modelo.

    Returns:
        El resultado del caso.
    """
    e = caso.esperado
    et = etiqueta(caso.id)
    r = objeto(respuesta)
    if not r:
        return _mal(f"{et}: no devolvió nada legible")
    obtenidas = []
    for linea in lista(r.get("lineas")):
        o = objeto(linea)
        obtenidas.append(
            {
                "referencia": normalizar_referencia(o.get("referencia")),
                "cantidad": leer_numero(_coalescer(o, "cantidad_cajas", "cantidad")),
                "precio": leer_numero(_coalescer(o, "precio_caja", "precio")),
                "bruta": texto(o.get("referencia")),
            }
        )
    for le in e["lineas"]:
        ref = normalizar_referencia(le["referencia"])
        candidatas = [o for o in obtenidas if o["referencia"] == ref]
        if not candidatas:
            return _mal(f"{et}: le faltó la línea de {le['referencia']} ({le['cantidad_cajas']} cajas)")
        con_cantidad = next(
            (o for o in candidatas if o["cantidad"] is not None and o["cantidad"] == le["cantidad_cajas"]),
            None,
        )
        if con_cantidad is None:
            c = candidatas[0]["cantidad"]
            leido = "¿?" if c is None else texto(c)
            return _mal(f"{et}: en {le['referencia']} leyó {leido} cajas donde ponía {le['cantidad_cajas']}")
        precio = con_cantidad["precio"]
        if le["precio_caja"] is not None and (precio is None or abs(precio - le["precio_caja"]) > 0.011):
            puso = "sin precio" if precio is None else formatear_euros(precio)
            return _mal(
                f"{et}: en {le['referencia']} puso {puso} donde la tarifa dice {formatear_euros(le['precio_caja'])}"
            )
    esperadas = {normalizar_referencia(le["referencia"]) for le in e["lineas"]}
    sobrante = next((o for o in obtenidas if o["referencia"] not in esperadas), None)
    if sobrante is not None:
        return _mal(f"{et}: se inventó una línea de {sobrante['bruta'] or '(sin referencia)'} que no está en el pedido")
    if len(obtenidas) > len(e["lineas"]):
        return _mal(f"{et}: duplicó líneas ({len(obtenidas)} donde había {len(e['lineas'])})")
    obligatorias = [i for i in e.get("incidencias", []) if i.get("obligatoria")]
    if obligatorias:
        incid = normalizar_texto(" | ".join(texto(x) for x in lista(r.get("incidencias"))))
        for inc in obligatorias:
            m = _REFERENCIA_INCIDENCIA_RE.search(inc["detalle"])
            ref_inc = m.group(0) if m else None
            inexistente = inc["tipo"] == "referencia-inexistente"
            pista = _PISTA_INEXISTENTE_RE if inexistente else _PISTA_PRECIO_RE
            menciona_ref = (
                normalizar_texto(ref_inc) in incid or normalizar_referencia(ref_inc).lower() in incid
                if ref_inc
                else True
            )
            if not incid or not pista.search(incid) or not menciona_ref:
                if inexistente:
                    return _mal(f"{et}: no avisó de que la referencia {ref_inc or ''} no existe en la tarifa")
                return _mal(f"{et}: no avisó de que el precio de {ref_inc or 'una línea'} no coincide con la tarifa")
    if not cliente_coincide(e["cliente"], r.get("cliente")):
        return _mal(f"{et}: identificó al cliente como «{texto(r.get('cliente')) or 'nadie'}» y era {e['cliente']}")
    return _bien()


# ===== resumir-correos =====


def puntuar_correo(caso: Caso, respuesta: Any) -> ResultadoCaso:
    """Puntúa un correo: categoría y urgencia exactas (acción y resumen no se puntúan).

    Args:
        caso: El caso, con el correo esperado.
        respuesta: Lo que ha devuelto el modelo.

    Returns:
        El resultado del caso.
    """
    e = caso.esperado
    et = etiqueta(caso.id)
    r = objeto(respuesta)
    if not r:
        return _mal(f"{et}: no devolvió nada legible")
    cat = _CATEGORIA_SEPARADOR_RE.sub("-", normalizar_texto(r.get("categoria")))
    urg = normalizar_texto(r.get("urgencia"))
    if cat != e["categoria"]:
        return _mal(
            f"{et}: lo clasificó como «{texto(r.get('categoria')) or 'nada'}» cuando era "
            f"{e['categoria']} ({e['resumen']})"
        )
    if urg != e["urgencia"]:
        return _mal(
            f"{et}: urgencia «{texto(r.get('urgencia')) or 'ninguna'}» donde era {e['urgencia']} ({e['resumen']})"
        )
    return _bien()


# ===== buscar-en-contrato =====


def cita_clausula(campo: str, aceptadas: list[str]) -> bool:
    """Si el campo cita alguna de las cláusulas aceptadas.

    Una cláusula numérica («9.2») tiene que aparecer como token entero (se admite un punto
    final: «9.2.», pero no «9.2.1»); una con letras («Anexo II») basta con que aparezca.

    Args:
        campo: Cláusula y respuesta del modelo, juntas.
        aceptadas: Cláusulas que valen para la pregunta.

    Returns:
        Si cita alguna.
    """
    c = normalizar_texto(campo)
    tokens = [t[:-1] if t.endswith(".") else t for t in _TOKEN_CLAUSULA_RE.split(c)]
    for a in aceptadas:
        an = normalizar_texto(a)
        if _LETRA_RE.search(an):
            if an in c:
                return True
        elif an in tokens:
            return True
    return False


def puntuar_contrato(caso: Caso, respuesta: Any) -> ResultadoCaso:
    """Puntúa una pregunta sobre el contrato: el dato (en respuesta, cláusula o cita) y la cláusula.

    Args:
        caso: El caso, con la pregunta esperada.
        respuesta: Lo que ha devuelto el modelo.

    Returns:
        El resultado del caso.
    """
    e = caso.esperado
    et = f"Contrato {e['id']}"
    r = objeto(respuesta)
    if not r:
        return _mal(f"{et}: no devolvió nada legible")
    todo = normalizar_texto(f"{texto(r.get('respuesta'))} {texto(r.get('clausula'))} {texto(r.get('cita'))}")
    for grupo in e["debe_contener_alguno"]:
        if not any(normalizar_texto(g) in todo for g in grupo):
            return _mal(
                f"{et}: a «{e['pregunta']}» respondió «{texto(r.get('respuesta'))[:80]}» y el contrato dice "
                f"{e['respuesta']} (cláusula {e['clausula']})"
            )
    if not cita_clausula(f"{texto(r.get('clausula'))} {texto(r.get('respuesta'))}", e["clausulas_aceptadas"]):
        return _mal(
            f"{et}: acertó el dato pero no citó la cláusula {e['clausula']}, así que no hay forma de "
            "comprobarlo sin releer"
        )
    return _bien()


# ===== clasificar-facturas =====


def puntuar_factura(caso: Caso, respuesta: Any) -> ResultadoCaso:
    """Puntúa una factura: total (±0,011 €), vencimiento y duplicada; lo demás no se puntúa.

    Args:
        caso: El caso, con la factura esperada.
        respuesta: Lo que ha devuelto el modelo.

    Returns:
        El resultado del caso.
    """
    e = caso.esperado
    et = etiqueta(caso.id)
    r = objeto(respuesta)
    if not r:
        return _mal(f"{et}: no devolvió nada legible")
    total = leer_numero(r.get("total"))
    if total is None or abs(total - e["total"]) > 0.011:
        nota = e.get("nota") or ""
        pista = f" ({nota[:-1] if nota.endswith('.') else nota})" if nota else ""
        puso = "sin importe" if total is None else formatear_euros(total)
        return _mal(f"{et}: total {puso} donde ponía {formatear_euros(e['total'])}{pista}")
    venc = leer_fecha(r.get("vencimiento"))
    if venc != e["vencimiento"]:
        return _mal(
            f"{et}: vencimiento {texto(r.get('vencimiento')) or 'en blanco'} donde tocaba {fecha_es(e['vencimiento'])}"
        )
    dup = leer_booleano(r.get("duplicada"))
    if dup is None or dup != e["duplicada"]:
        if e["duplicada"]:
            return _mal(f"{et}: no vio que la {e['numero']} de {e['proveedor']} ya estaba contabilizada (duplicada)")
        return _mal(f"{et}: marcó como duplicada la {e['numero']} de {e['proveedor']}, que es nueva")
    return _bien()


# ===== redactar-recordatorio =====

_QUE_RECORDATORIO = ("el número de factura", "el importe pendiente", "la fecha de vencimiento")


def puntuar_recordatorio(caso: Caso, respuesta: Any) -> ResultadoCaso:
    """Puntúa un recordatorio de cobro por reglas, no por gusto.

    Tiene que mencionar la factura, el importe y el vencimiento; cumplir la expresión
    obligatoria del tono (el último aviso fija plazo y advierte); no usar lo prohibido en ese
    tono; no pasar de ``max_palabras``; nombrar a la persona; firmar como la empresa.

    Args:
        caso: El caso, con las reglas del recordatorio.
        respuesta: Lo que ha devuelto el modelo (objeto con asunto y cuerpo, o una cadena).

    Returns:
        El resultado del caso.
    """
    e = caso.esperado
    et = etiqueta(caso.id)
    r = objeto(respuesta)
    cuerpo = respuesta if isinstance(respuesta, str) else f"{texto(r.get('asunto'))}\n{texto(r.get('cuerpo'))}"
    if not js.recortar(cuerpo):
        return _mal(f"{et}: no escribió nada")
    n = normalizar_texto(cuerpo)
    reglas = e["reglas"]
    for i, grupo in enumerate(reglas["debe_contener_alguno"]):
        if not any(normalizar_texto(g) in n for g in grupo):
            if i == 0:
                detalle = e["factura"]
            elif i == 1:
                detalle = formatear_euros(e["importe_pendiente"])
            else:
                detalle = fecha_es(e["vencimiento"])
            que = _QUE_RECORDATORIO[i] if i < len(_QUE_RECORDATORIO) else "un dato"
            return _mal(f"{et}: no menciona {que} ({detalle})")
    for exp in reglas["debe_contener_expresion"]:
        if not re.search(exp, n, re.IGNORECASE):
            return _mal(
                f"{et}: un último aviso tiene que fijar plazo y advertir de suspensión o intereses, y no lo hace"
            )
    for p in reglas["no_debe_contener"]:
        if normalizar_texto(p) in n:
            return _mal(f"{et}: usa «{p}» en un recordatorio de tono {e['tono']} a {e['cliente']}")
    palabras = len([w for w in _PALABRAS_RE.split(cuerpo) if w])
    if palabras > reglas["max_palabras"]:
        return _mal(f"{et}: {palabras} palabras para reclamar una factura; nadie lo lee entero")
    if normalizar_texto(reglas["debe_nombrar_cliente"]) not in n:
        return _mal(f"{et}: no se dirige a {e['contacto']} por su nombre")
    if normalizar_texto(reglas["debe_firmar"]) not in n:
        return _mal(f"{et}: no firma como la empresa (Marjal Blanca)")
    return _bien()


# ===== puntuación de una tarea entera =====

COMPARADORES: Final[dict[str, Any]] = {
    "extraer-pedidos": puntuar_pedido,
    "resumir-correos": puntuar_correo,
    "buscar-en-contrato": puntuar_contrato,
    "clasificar-facturas": puntuar_factura,
    "redactar-recordatorio": puntuar_recordatorio,
}


def puntuar_caso(tarea: str, caso: Caso, respuesta: Any) -> ResultadoCaso:
    """Puntúa un caso con el comparador de su tarea.

    Args:
        tarea: Identificador de la tarea.
        caso: El caso.
        respuesta: Lo que ha devuelto el modelo; ``AUSENTE`` si la llamada no devolvió nada
            válido (``None`` es un ``null`` de verdad y llega al comparador).

    Returns:
        El resultado del caso.

    Raises:
        KeyError: Si la tarea no tiene comparador.
    """
    if respuesta is AUSENTE:
        return _mal(f"{etiqueta(caso.id)}: el modelo no devolvió una respuesta válida")
    return COMPARADORES[tarea](caso, respuesta)


def puntuar(tarea: str, casos: list[Caso], respuestas: list[Any]) -> Puntuacion:
    """Puntúa una tarea entera: ``respuestas[i]`` responde a ``casos[i]``.

    Args:
        tarea: Identificador de la tarea.
        casos: Los casos, en orden.
        respuestas: Las respuestas, en el mismo orden; si faltan, cuentan como ``AUSENTE``.

    Returns:
        Aciertos, los tres primeros fallos y todos los fallos.
    """
    aciertos = 0
    todos: list[str] = []
    for i, caso in enumerate(casos):
        respuesta = respuestas[i] if i < len(respuestas) else AUSENTE
        r = puntuar_caso(tarea, caso, respuesta)
        if r.ok:
            aciertos += 1
        else:
            todos.append(r.fallo or f"{etiqueta(caso.id)}: fallo sin detalle")
    return Puntuacion(aciertos=aciertos, fallos=todos[:3], todos_los_fallos=todos)


# ===== veredicto y nota =====


def veredicto_por_reglas(aciertos: int, casos: int, coste_eur: float, sin_respuesta: int = 0) -> str:
    """El veredicto según los umbrales del contrato.

    «lo-usaria-el-lunes» con el 90 % de aciertos y 5 céntimos por caso como mucho;
    «todavia-no» a partir del 60 % (o si la mayoría de los casos no tuvo respuesta legible:
    no se ha medido lo que sabe la herramienta); «humo» por debajo.

    Args:
        aciertos: Casos bien.
        casos: Casos probados.
        coste_eur: Coste total de la prueba.
        sin_respuesta: Casos sin respuesta legible.

    Returns:
        ``"lo-usaria-el-lunes"``, ``"todavia-no"`` o ``"humo"``.
    """
    if not casos:
        return "todavia-no"
    if sin_respuesta >= math.ceil(casos * 0.8):
        return "todavia-no"
    tasa = aciertos / casos
    coste_caso = coste_eur / casos
    if tasa >= UMBRALES["aciertos_lunes"] and coste_caso <= UMBRALES["coste_caso_lunes_eur"]:
        return "lo-usaria-el-lunes"
    if tasa >= UMBRALES["aciertos_humo"]:
        return "todavia-no"
    return "humo"


def nota_por_reglas(
    veredicto: str,
    aciertos: int,
    casos: int,
    coste_eur: float,
    fallos: list[str],
    sin_respuesta: int = 0,
    errores_servicio: int = 0,
) -> str:
    """La nota de una frase que acompaña al veredicto, con las mismas palabras que el blog.

    Args:
        veredicto: El veredicto de ``veredicto_por_reglas``.
        aciertos: Casos bien.
        casos: Casos probados.
        coste_eur: Coste total de la prueba.
        fallos: Los fallos publicados (se cita el primero como ejemplo).
        sin_respuesta: Casos sin respuesta legible.
        errores_servicio: De esos, cuántos fueron errores del servicio (HTTP/red).

    Returns:
        La nota.
    """
    fallados = casos - aciertos
    if casos and errores_servicio >= math.ceil(casos * 0.8):
        return (
            f"El servicio no contestó en {errores_servicio} de {casos} casos (errores de red o del "
            "proveedor): no se ha medido nada. Lo repetiremos."
        )
    if casos and sin_respuesta >= math.ceil(casos * 0.8):
        return (
            f"No devolvió una respuesta que se pudiera leer en {sin_respuesta} de {casos} casos. Puede ser "
            "cosa de cómo se lo pedimos y no de lo que sabe: lo repetiremos antes de darlo por malo."
        )
    coste_caso = coste_eur / casos if casos else 0
    centimos = f"{js.a_fijo(coste_caso * 100, 1).replace('.', ',')} céntimos por caso"
    primer_fallo = f" Ejemplo: {fallos[0]}." if fallos and fallos[0] else ""
    if veredicto == "lo-usaria-el-lunes":
        if fallados == 0:
            return (
                f"Acertó los {casos} casos a {centimos}; lo pondría a trabajar el lunes con alguien mirando "
                "por encima la primera semana."
            )
        return (
            f"Acertó {aciertos} de {casos} a {centimos}; sirve el lunes si una persona repasa los casos con "
            f"incidencia.{primer_fallo}"
        )
    if veredicto == "todavia-no":
        if casos and aciertos / casos >= UMBRALES["aciertos_lunes"]:
            return (
                f"Acierta ({aciertos} de {casos}) pero sale a {centimos}: para este volumen no compensa "
                "frente a hacerlo a mano."
            )
        return f"Falló {fallados} de {casos}: hay que revisar cada resultado y entonces no ahorra tiempo.{primer_fallo}"
    return f"Falló {fallados} de {casos}; no vale para esto todavía.{primer_fallo}"
