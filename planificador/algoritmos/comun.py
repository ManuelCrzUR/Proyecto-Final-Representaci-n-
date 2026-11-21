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
from planificador.core.estado import Estado
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


def _dominio_base(instancia, bloque_id) -> tuple:
    """Posiciones legales en un estado VACÍO que respetan A y W.

    No depende de la ocupación, así que se calcula una vez por bloque y se
    memoiza en la propia instancia (inmutable), como ``costo._gamma``.
    Conserva el orden (dia, franja, salon) de ``posiciones_legales``.
    """
    cache = instancia.__dict__.setdefault("_dominio_base_comun", {})
    base = cache.get(bloque_id)
    if base is None:
        b = instancia.bloque[bloque_id]
        base = tuple(p for p in posiciones_legales(Estado(instancia), bloque_id)
                     if _respeta_unarias(instancia, b, p))
        cache[bloque_id] = base
    return base


def _salon_libre(estado, bloque_id, duracion, pos) -> bool:
    """Celdas libres en el salón (el bloque se ignora a sí mismo)."""
    if estado.instancia.salon[pos.salon].virtual:
        return True
    for celda in celdas_de(pos, duracion):
        otro = estado.ocupante(pos.salon, celda)
        if otro is not None and otro != bloque_id:
            return False
    return True


def dominio_unario(estado, bloque_id) -> list:
    """Posiciones legales (salón libre, tipo, capacidad) que respetan A y W.

    Equivale a filtrar ``posiciones_legales`` por A y W, pero parte del
    dominio base memoizado y solo revisa la ocupación de salones.
    """
    inst = estado.instancia
    dur = inst.bloque[bloque_id].duracion
    return [p for p in _dominio_base(inst, bloque_id)
            if _salon_libre(estado, bloque_id, dur, p)]


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
