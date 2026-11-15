"""Tests de beam search."""

import pytest

from planificador.algoritmos.base import Limites
from planificador.algoritmos.beam import BeamSearch
from planificador.core.estado import Estado
from planificador.core.validador import validar
from planificador.io_datos.sintetico import generar_instancia
from tests.fixtures.instancias_mini import (
    mini_factible, mini_infactible, mini_reparacion, mini_virtual)


@pytest.mark.parametrize("fabrica", [mini_factible, mini_reparacion,
                                     mini_virtual])
def test_mini_factibles_v0(fabrica):
    inst = fabrica()["instancia"]
    res = BeamSearch(ancho=5).resolver(inst)
    assert res.v == 0 and res.terminado_por == "meta"
    assert validar(inst, res.asignacion).violaciones.total == 0
    assert res.extra["ancho"] == 5


def test_mini_infactible_v1():
    res = BeamSearch().resolver(mini_infactible()["instancia"])
    assert res.v == 1 and res.extra["saltados"] == 1


@pytest.mark.parametrize("n, ancho", [(20, 10), (50, 5), (100, 2)])
def test_sinteticas_v0(n, ancho):
    inst, _ = generar_instancia(n, 1)
    res = BeamSearch(ancho=ancho).resolver(
        inst, limites=Limites(max_segundos=60))
    assert res.v == 0, (res.terminado_por, res.nodos_expandidos)
    assert validar(inst, res.asignacion).violaciones.total == 0
    assert res.extra["niveles"] == n


def test_ancho_uno_corre():
    inst, _ = generar_instancia(20, 3)
    res = BeamSearch(ancho=1).resolver(inst)
    assert res.v == 0 and res.extra["ancho"] == 1
    # un solo nodo por nivel: tantas expansiones como bloques
    assert res.nodos_expandidos == 20


def test_ancho_invalido():
    with pytest.raises(ValueError):
        BeamSearch(ancho=0)


def test_mayor_ancho_g_no_peor_en_promedio():
    """Aserción suave: el promedio de g con ancho 10 <= el de ancho 1.

    No es una garantía teórica (beam es incompleto y no monótono en el
    ancho), pero con 3 semillas el haz ancho explora un superconjunto de
    candidatos por nivel y en la práctica no empeora en promedio.
    """
    g1, g10 = [], []
    for semilla in (1, 2, 3):
        inst, _ = generar_instancia(20, semilla)
        g1.append(_g(inst, 1))
        g10.append(_g(inst, 10))
    assert sum(g10) / 3 <= sum(g1) / 3 + 1e-9


def _g(inst, ancho):
    from planificador.algoritmos.informada import costo_camino
    res = BeamSearch(ancho=ancho).resolver(inst)
    return costo_camino(inst, res.asignacion, ())


def test_presupuesto_limite_nodos():
    inst, _ = generar_instancia(20, 1)
    res = BeamSearch(ancho=3).resolver(inst, limites=Limites(max_nodos=4))
    assert res.terminado_por == "limite_nodos"
    assert res.nodos_expandidos == 4
    assert res.v == len(inst.bloques) - len(res.asignacion)


def test_determinismo_y_no_muta():
    inst, _ = generar_instancia(20, 2)
    est = Estado(inst)
    a = BeamSearch(ancho=4).resolver(inst, estado_inicial=est)
    b = BeamSearch(ancho=4).resolver(inst)
    assert a.asignacion == b.asignacion
    assert (a.nodos_expandidos, a.nodos_generados) == (
        b.nodos_expandidos, b.nodos_generados)
    assert not est.asignacion


def test_bloques_fijos():
    datos = mini_reparacion()
    inst = datos["instancia"]
    fijo = {"B1": datos["solucion"]["B1"]}
    res = BeamSearch().resolver(inst, estado_inicial=Estado(inst, fijo))
    assert res.asignacion["B1"] == fijo["B1"] and res.v == 0


def test_traza_con_fotos():
    inst, _ = generar_instancia(20, 1)
    res = BeamSearch(ancho=3).resolver(inst)
    tipos = {e.tipo for e in res.traza.eventos}
    assert {"expandir", "frontera", "podar", "solucion", "fin"} <= tipos
    exp = [e for e in res.traza.eventos if e.tipo == "expandir"]
    assert all(e.asignacion is not None for e in exp)
    fr = [e for e in res.traza.eventos if e.tipo == "frontera"]
    assert all(e.tam_frontera <= 3 for e in fr)
