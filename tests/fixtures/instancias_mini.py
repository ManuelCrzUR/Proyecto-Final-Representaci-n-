"""Reexporta las instancias mini de ``planificador.datos_demo``.

El código vive en ``planificador/datos_demo.py``, que también usan la app y el
notebook. Este módulo se conserva para que los tests sigan importando desde
``tests.fixtures.instancias_mini``.
"""

from planificador.datos_demo import *  # noqa: F401,F403
from planificador.datos_demo import (  # noqa: F401
    TODAS_LAS_FIXTURES,
    mini_factible,
    mini_infactible,
    mini_reparacion,
    mini_sin_disponibilidad,
    mini_virtual,
)
