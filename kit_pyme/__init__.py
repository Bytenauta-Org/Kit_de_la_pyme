"""Kit de la pyme: el banco de pruebas del blog «A la última» (Bytenauta), en Python.

Cinco tareas administrativas de una conservera inventada, con la respuesta correcta
conocida y una puntuación determinista, portada regla por regla desde el pipeline del
blog (``src/pruebas/puntuar.ts`` e ``index.ts``). Las cifras que salen de aquí son
comparables con las que publica el blog cada semana.

Uso rápido::

    python -m kit_pyme tareas
    python -m kit_pyme casos clasificar-facturas
    python -m kit_pyme puntuar clasificar-facturas respuestas.jsonl
    python -m kit_pyme ejecutar --tarea clasificar-facturas --endpoint URL --modelo M --clave-env VAR
    python -m kit_pyme verificar
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
