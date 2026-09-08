"""Ejecuta una tarea entera contra un modelo: caso a caso, cuatro a la vez, midiendo.

Es ``probarTarea`` de ``src/pruebas/index.ts`` del blog: se lanzan los casos con una
concurrencia de 4 (si no, los segundos no son comparables), cada uno se puntúa con su
comparador, y al final se suman tokens y coste (intentos perdidos incluidos), se mide el
tiempo de pared del lote y se construye el ``ResultadoPrueba``. Un 4xx distinto de 429
marca el modelo como no disponible: el resto de casos se salta y la tarea no produce
resultado.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from kit_pyme import javascript as js
from kit_pyme.cliente import Cliente, ErrorCliente, Peticion
from kit_pyme.informe import Informe, Registro, construir_informe
from kit_pyme.puntuacion import AUSENTE
from kit_pyme.tareas import Caso, Tarea

#: Llamadas simultáneas al modelo, las mismas que el blog.
CONCURRENCIA = 4


class ModeloNoDisponible(Exception):
    """El endpoint respondió un 4xx: el modelo no existe o no está autorizado."""

    def __init__(self, modelo: str, error: ErrorCliente) -> None:
        """Construye el error.

        Args:
            modelo: Id del modelo.
            error: El error de la llamada que lo descubrió.
        """
        super().__init__(f"el endpoint respondió {error.estado} para {modelo}: no disponible por API todavía")
        self.modelo = modelo
        self.error = error


def ejecutar_tarea(
    cliente: Cliente,
    tarea: Tarea,
    modelo: str,
    modelo_api: str | None = None,
    casos: list[Caso] | None = None,
    concurrencia: int = CONCURRENCIA,
    novedad_url: str = "",
    modo_barato: bool = False,
) -> Informe:
    """Prueba una tarea con un modelo y devuelve el informe.

    Args:
        cliente: El endpoint ya configurado.
        tarea: La tarea.
        modelo: Id con el que se etiqueta el resultado («anthropic/claude-haiku-4-5»).
        modelo_api: Nombre que se envía en ``model``; por defecto, el id sin prefijo de proveedor.
        casos: Casos a probar; por defecto todos los de la tarea.
        concurrencia: Llamadas simultáneas.
        novedad_url: URL de la novedad, si la prueba es de una (vacía en el kit).
        modo_barato: Si ``casos`` es una muestra recortada (cambia el nombre de la tarea).

    Returns:
        El informe con el resultado y el detalle por caso.

    Raises:
        ModeloNoDisponible: Si el endpoint devolvió un 4xx distinto de 429.
    """
    casos = tarea.preparar() if casos is None else casos
    system = tarea.system
    nombre_api = modelo_api if modelo_api is not None else modelo.split("/", 1)[-1]
    no_disponible: list[ErrorCliente] = []
    candado = threading.Lock()

    def un_caso(caso: Caso) -> Registro:
        with candado:
            if no_disponible:
                return Registro(
                    id=caso.id,
                    ok=False,
                    respuesta=AUSENTE,
                    esperado=caso.esperado,
                    error="saltado: modelo no disponible",
                    error_servicio=True,
                )
        t0 = time.monotonic()
        peticion = Peticion(
            system=system,
            user=caso.entrada,
            esquema=tarea.esquema,
            max_tokens=tarea.max_tokens,
            temperatura=0,
        )
        try:
            r = cliente.llamar(modelo, nombre_api, peticion)
        except ErrorCliente as e:
            if e.no_disponible:
                with candado:
                    no_disponible.append(e)
            return Registro(
                id=caso.id,
                ok=False,
                respuesta=AUSENTE,
                esperado=caso.esperado,
                segundos=time.monotonic() - t0,
                uso=e.uso,
                error=str(e),
                error_estado=e.estado,
                error_servicio=e.es_del_servicio,
            )
        return Registro(
            id=caso.id,
            ok=False,
            respuesta=r.datos,
            esperado=caso.esperado,
            texto_modelo=r.texto,
            segundos=time.monotonic() - t0,
            uso=r.uso,
        )

    inicio = time.monotonic()
    with ThreadPoolExecutor(max_workers=max(1, min(concurrencia, len(casos) or 1))) as hilos:
        registros = list(hilos.map(un_caso, casos))
    milisegundos = int((time.monotonic() - inicio) * 1000)
    segundos = js.redondear(milisegundos / 100) / 10
    if no_disponible:
        raise ModeloNoDisponible(modelo, no_disponible[0])
    return construir_informe(
        tarea,
        casos,
        registros,
        segundos,
        modelo,
        novedad_url=novedad_url,
        modo_barato=modo_barato,
    )
