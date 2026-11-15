"""Registro único de algoritmos (dueño: orquestador).

Lo usan la interfaz, los experimentos y el notebook para listar y construir
solvers por nombre, con sus parámetros por defecto y una descripción.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .backtracking import Backtracking
from .beam import BeamSearch
from .informada import AEstrella, Avara


@dataclass(frozen=True)
class EntradaSolver:
    clase: type
    descripcion: str
    parametros: dict = field(default_factory=dict)  # valores por defecto
    # parámetros ajustables desde la interfaz: nombre -> (tipo, opciones|rango)
    ajustables: dict = field(default_factory=dict)


REGISTRO = {
    "backtracking": EntradaSolver(
        Backtracking,
        "Backtracking (CSP) con MRV + grado y forward checking.",
        {"modo": "primera", "mrv": True, "forward_checking": True},
        {"modo": ("opcion", ("primera", "optimizar")),
         "mrv": ("bool", None), "forward_checking": ("bool", None)},
    ),
    "a_estrella": EntradaSolver(
        AEstrella,
        "A* con heurística admisible y consistente (óptimo en costo aditivo).",
        {"peso_h": 1.0},
        {"peso_h": ("float", (1.0, 5.0))},
    ),
    "avara": EntradaSolver(
        Avara,
        "Búsqueda avara: heurística de distancia a la meta (no admisible).",
        {"peso_distancia": 1.0},
        {"peso_distancia": ("float", (0.1, 10.0))},
    ),
    "beam": EntradaSolver(
        BeamSearch,
        "Beam search: conserva los k mejores nodos por nivel (g + h).",
        {"ancho": 10},
        {"ancho": ("int", (1, 50))},
    ),
}

NOMBRES = tuple(REGISTRO)


def crear_solver(nombre: str, **parametros):
    """Crea el solver ``nombre`` con sus parámetros por defecto + ``parametros``."""
    if nombre not in REGISTRO:
        raise KeyError(f"Algoritmo desconocido: {nombre}. Opciones: {NOMBRES}")
    entrada = REGISTRO[nombre]
    return entrada.clase(**{**entrada.parametros, **parametros})
