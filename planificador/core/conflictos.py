"""Grafo de conflictos Γ entre bloques."""

from __future__ import annotations

from planificador.core.modelo import Instancia


def construir_conflictos(instancia: Instancia) -> dict[str, frozenset[str]]:
    """Construye Γ: bloque_id -> conjunto de bloques vecinos.

    Dos bloques distintos son vecinos si comparten ``docente_id`` (no None) o
    al menos un grupo. Un bloque nunca es vecino de sí mismo. Todos los
    bloques de la instancia aparecen como clave (posiblemente con conjunto
    vacío). La relación es simétrica.
    """
    por_docente: dict[str, list[str]] = {}
    por_grupo: dict[str, list[str]] = {}
    for b in instancia.bloques:
        if b.docente_id is not None:
            por_docente.setdefault(b.docente_id, []).append(b.id)
        for g in b.grupos:
            por_grupo.setdefault(g, []).append(b.id)

    vecinos: dict[str, set[str]] = {b.id: set() for b in instancia.bloques}
    for indice in (por_docente, por_grupo):
        for ids in indice.values():
            for m in ids:
                vecinos[m].update(ids)
    for m, conjunto in vecinos.items():
        conjunto.discard(m)
    return {m: frozenset(c) for m, c in vecinos.items()}


def grado(conflictos: dict[str, frozenset[str]], bloque_id: str) -> int:
    """Número de vecinos del bloque en Γ."""
    return len(conflictos[bloque_id])
