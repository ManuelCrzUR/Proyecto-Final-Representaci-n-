"""Regresión: la semana tipo (herramientas/smoke_semana.py)."""

import pytest

from herramientas.smoke_semana import (
    ejecutar, instancia_semana, solucion_referencia)
from planificador.algoritmos.registro import NOMBRES
from planificador.core.validador import validar


def test_referencia_es_valida():
    assert validar(instancia_semana(), solucion_referencia()).violaciones.total == 0


@pytest.mark.parametrize("variante,v_esperado", [("factible", 0), ("imposible", 1)])
def test_todos_los_algoritmos(variante, v_esperado):
    inst = instancia_semana(variante)
    resultados = ejecutar(variante, segundos=10)
    assert set(resultados) == set(NOMBRES)
    for nombre, r in resultados.items():
        assert r.v == v_esperado, nombre
        assert validar(inst, r.asignacion).violaciones.total == r.v
        # Cada bloque ubicado queda en un día en que su docente está disponible.
        dias_docente = {"D1": {1}, "D2": {2, 4}, "D3": {3}, "D4": {5}, "D5": {0}}
        for b, p in r.asignacion.items():
            doc = inst.bloque[b].docente_id
            if doc is not None:
                assert p.dia in dias_docente[doc], (nombre, b)
    if variante == "imposible":
        for r in resultados.values():
            assert len(r.asignacion) == len(inst.bloques) - 1
            sin_ubicar = set(inst.bloque) - set(r.asignacion)
            assert sin_ubicar <= {"PERF-T", "PERF-T2"}  # uno de los dos de D3
