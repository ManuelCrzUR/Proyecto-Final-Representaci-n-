"""Ejecución de solvers para la interfaz (módulo puro, sin Streamlit).

Encapsula los dos escenarios (construcción y reparación) y la comparación
de varios algoritmos, usando ``registro.crear_solver``.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from planificador.algoritmos.base import Limites, Resultado
from planificador.algoritmos.registro import REGISTRO, crear_solver
from planificador.algoritmos.reparacion import bloques_invalidos, reparar
from planificador.algoritmos.reproduccion import cuadros_de_resultado
from planificador.core.conflictos import construir_conflictos
from planificador.core.modelo import Instancia
from planificador.io_datos.sintetico import perturbar_disponibilidad

_CONTADOR = itertools.count(1)


@dataclass
class Ejecucion:
    """Resultado de una corrida más el contexto necesario para mostrarla."""

    uid: int
    escenario: str                  # "construccion" | "reparacion"
    algoritmo: str
    parametros: dict
    instancia: Instancia            # la usada (perturbada si es reparación)
    resultado: Resultado
    conflictos: dict
    vigente: dict = field(default_factory=dict)
    inicial: dict = field(default_factory=dict)

    def cuadros(self, max_cuadros: int | None = None) -> list:
        """Cuadros de la animación (la traza termina en la solución)."""
        return cuadros_de_resultado(self.resultado, self.inicial or None,
                                    max_cuadros)


def limites_desde(max_segundos, max_nodos) -> Limites:
    """``Limites`` con valores 0/None = sin límite."""
    return Limites(max_nodos=int(max_nodos) if max_nodos else None,
                   max_segundos=float(max_segundos) if max_segundos else None)


def ejecutar_construccion(instancia: Instancia, algoritmo: str,
                          parametros: dict | None = None,
                          limites: Limites | None = None) -> Ejecucion:
    """Construye un horario desde cero con el algoritmo elegido."""
    parametros = dict(parametros or {})
    solver = crear_solver(algoritmo, **parametros)
    res = solver.resolver(instancia, None, limites or Limites())
    return Ejecucion(next(_CONTADOR), "construccion", algoritmo, parametros,
                     instancia, res, construir_conflictos(instancia))


def ejecutar_reparacion(instancia: Instancia, vigente: dict, algoritmo: str,
                        parametros: dict | None = None,
                        limites: Limites | None = None, *, semilla: int = 0,
                        num_docentes: int = 1,
                        fraccion: float = 0.5) -> Ejecucion:
    """Perturba la disponibilidad y repara el horario ``vigente``."""
    if not vigente:
        raise ValueError("No hay horario vigente que reparar.")
    parametros = dict(parametros or {})
    perturbada = perturbar_disponibilidad(
        instancia, vigente, semilla, num_docentes=num_docentes,
        fraccion=fraccion)
    solver = crear_solver(algoritmo, **parametros)
    res = reparar(perturbada, vigente, solver, limites or Limites())
    invalidos = bloques_invalidos(perturbada, vigente)
    inicial = {b: p for b, p in vigente.items()
               if b in perturbada.bloque and b not in invalidos}
    return Ejecucion(next(_CONTADOR), "reparacion", algoritmo, parametros,
                     perturbada, res, construir_conflictos(perturbada),
                     dict(vigente), inicial)


def comparar(instancia: Instancia, configuraciones: list,
             limites: Limites | None = None) -> list:
    """Corre varias configuraciones ``(algoritmo, parametros)``.

    Devuelve una lista de ``(etiqueta, Ejecucion | None, error | None)``;
    un fallo de un solver no impide correr los demás.
    """
    salida = []
    for algoritmo, parametros in configuraciones:
        etiqueta = algoritmo
        try:
            ej = ejecutar_construccion(instancia, algoritmo, parametros,
                                       limites)
            salida.append((etiqueta, ej, None))
        except Exception as exc:  # noqa: BLE001 - se informa en la interfaz
            salida.append((etiqueta, None, f"{type(exc).__name__}: {exc}"))
    return salida


def fila_resumen(etiqueta: str, ej: Ejecucion) -> dict:
    """Fila de la tabla comparativa."""
    r = ej.resultado
    return {"algoritmo": etiqueta, "v": r.v, "f": round(r.f, 3),
            "F": round(r.F, 3), "tiempo_s": round(r.tiempo_s, 4),
            "nodos_expandidos": r.nodos_expandidos,
            "nodos_generados": r.nodos_generados,
            "terminado_por": r.terminado_por, "exito": r.exito}


def parametros_por_defecto(algoritmo: str) -> dict:
    """Parámetros por defecto del registro."""
    return dict(REGISTRO[algoritmo].parametros)
