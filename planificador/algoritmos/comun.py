"""Utilidades compartidas por los solvers (dueño: orquestador).

* ``dominio_unario``: posiciones legales que no violan A (disponibilidad) ni W
  (ventana). Es el filtrado inicial de restricciones unarias del CSP.
* ``consistente``: una posición no se cruza con bloques vecinos en Γ ya ubicados.
* ``dominio_consistente``: dominio unario filtrado por consistencia con el estado
  (base del forward checking y de la expansión de A*/beam).
* ``elegir_mrv``: variable con menor dominio, desempate por mayor grado en Γ y
  luego por id (determinista).
* ``resultado_desde``: arma un ``Resultado`` evaluando con ``core.costo``.
"""

from __future__ import annotations

from planificador.core import costo
from planificador.core.acciones import posiciones_legales
from planificador.core.modelo import celdas_de

from .base import Resultado


def _respeta_unarias(instancia, bloque, pos) -> bool:
    celdas = celdas_de(pos, bloque.duracion)
    if bloque.docente_id is not None:
        disp = instancia.docente[bloque.docente_id].disponibilidad
        if any(c not in disp for c in celdas):
            return False
    for g in bloque.grupos:
        ventana = instancia.grupo[g].ventana
        if any(c not in ventana for c in celdas):
            return False
    return True


def dominio_unario(estado, bloque_id) -> list:
    """Posiciones legales (salón libre, tipo, capacidad) que respetan A y W."""
    inst = estado.instancia
    b = inst.bloque[bloque_id]
    return [p for p in posiciones_legales(estado, bloque_id)
            if _respeta_unarias(inst, b, p)]


def consistente(estado, bloque_id, pos) -> bool:
    """True si ubicar el bloque en ``pos`` no cruza docente ni grupo ocupados."""
    b = estado.instancia.bloque[bloque_id]
    for celda in celdas_de(pos, b.duracion):
        if (b.docente_id is not None
                and estado.ocupacion_docente(b.docente_id, celda) > 0):
            return False
        if any(estado.ocupacion_grupo(g, celda) > 0 for g in b.grupos):
            return False
    return True


def dominio_consistente(estado, bloque_id) -> list:
    """Dominio unario filtrado por consistencia con lo ya ubicado."""
    return [p for p in dominio_unario(estado, bloque_id)
            if consistente(estado, bloque_id, p)]


def elegir_mrv(dominios: dict, conflictos: dict):
    """Bloque con dominio mínimo; desempate por grado en Γ (mayor) y por id."""
    if not dominios:
        return None
    return min(dominios, key=lambda b: (len(dominios[b]),
                                        -len(conflictos.get(b, ())), b))


def resultado_desde(algoritmo, estado, presupuesto, terminado_por, traza,
                    parametros=None, extra=None) -> Resultado:
    """Construye el ``Resultado`` evaluando el estado con ``core.costo``."""
    return Resultado(
        algoritmo=algoritmo,
        asignacion=dict(estado.asignacion),
        violaciones=costo.violaciones(estado),
        f=costo.f(estado),
        F=costo.F(estado),
        tiempo_s=presupuesto.transcurrido(),
        nodos_expandidos=presupuesto.nodos_expandidos,
        nodos_generados=presupuesto.nodos_generados,
        terminado_por=terminado_por,
        traza=traza,
        parametros=dict(parametros or {}),
        extra=dict(extra or {}),
    )
