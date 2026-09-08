"""Pruebas del kit de la pyme.

Es un paquete para que los módulos puedan importarse entre sí («from tests.conftest import …»):
sin esto, pytest los encuentra al ejecutarlo desde la raíz pero falla en cualquier otro sitio, y en
la CI el módulo «tests» no existía.
"""
