"""Tests del escenario de reparación (estabilidad / perturbación mínima)."""

import pytest

from planificador.algoritmos.backtracking import Backtracking
from planificador.algoritmos.base import Limites
from planificador.algoritmos.beam import BeamSearch
from planificador.algoritmos.informada import AEstrella, Avara
from planificador.algoritmos.reparacion import bloques_invalidos, reparar
from planificador.core.modelo import (
    Bloque, Dia, Docente, Franja, Grupo, Instancia, Posicion, Salon)
from planificador.core.validador import validar
from planificador.io_datos.sintetico import (
    generar_instancia, perturbar_disponibilidad)
from tests.fixtures.instancias_mini import mini_reparacion

LIM = Limites(max_nodos=50_000, max_segundos=20.0)

SOLVERS = [
    pytest.param(lambda: Backtracking(), id="backtracking"),
    pytest.param(lambda: AEstrella(), id="astar"),
    pytest.param(lambda: Avara(), id="avara"),
    pytest.param(lambda: BeamSearch(ancho=3), id="beam3"),
]


def _casos(n, semilla):
    inst, sol = generar_instancia(n, semilla)
    return perturbar_disponibilidad(inst, sol, semilla), sol


@pytest.mark.parametrize("fabrica", SOLVERS)
def test_mini_reparacion(fabrica):
    d = mini_reparacion()
    inst, vigente = d["instancia"], d["solucion_vigente"]
    assert bloques_invalidos(inst, vigente) == frozenset({"B1", "B3"})
    res = reparar(inst, vigente, fabrica(), LIM)
    assert res.v == 0
    assert validar(inst, res.asignacion).violaciones.total == 0
    assert res.asignacion["B2"] == vigente["B2"]
    assert res.extra["invalidos"] == 2
    assert res.extra["movidos"] == 2
    assert res.extra["radio"] == 0
    assert res.traza.eventos[-1].tipo == "fin"


def test_bloques_invalidos_vigente_valido_vacio():
    d = mini_reparacion()
    inst = d["instancia"]
    assert bloques_invalidos(inst, d["solucion"]) == frozenset()


# Semillas cuya instancia perturbada sigue siendo factible (verificado con
# backtracking exhaustivo desde cero). Con las semillas 1 (n=50 y 100), 3 y 5
# (n=100) la perturbación vuelve la instancia infactible: ver el test siguiente.
CASOS_FACTIBLES = [(50, 2), (50, 3), (50, 4), (50, 5), (100, 2), (100, 4)]


@pytest.mark.parametrize("n,semilla", CASOS_FACTIBLES)
@pytest.mark.parametrize("fabrica", SOLVERS[:1] + SOLVERS[2:3])
def test_sinteticas(n, semilla, fabrica):
    nueva, sol = _casos(n, semilla)
    assert bloques_invalidos(nueva, sol)
    res = reparar(nueva, sol, fabrica(), LIM)
    assert res.v == 0
    assert validar(nueva, res.asignacion).violaciones.total == 0
    assert res.extra["movidos"] < n
    assert res.extra["estabilidad"] > 0.4


@pytest.mark.parametrize("n,semilla", [(50, 1), (100, 1)])
def test_instancia_infactible_no_empeora(n, semilla):
    """Si la perturbación vuelve infactible la instancia, reparar no deja
    más violaciones que resolver desde cero (v mínimo = 2 con backtracking)."""
    nueva, sol = _casos(n, semilla)
    solver = Backtracking()
    cero = solver.resolver(nueva, None, LIM)
    rep = reparar(nueva, sol, solver, LIM)
    assert cero.v > 0
    assert rep.v <= cero.v
    assert rep.extra["intentos"] == 3


@pytest.mark.parametrize("n,semilla", [(50, 2), (50, 4), (100, 2)])
def test_reparar_mueve_menos_que_desde_cero(n, semilla):
    nueva, sol = _casos(n, semilla)
    solver = Backtracking()
    rep = reparar(nueva, sol, solver, LIM)
    cero = solver.resolver(nueva, None, LIM)
    movidos_cero = sum(1 for b, p in sol.items()
                       if cero.asignacion.get(b) != p)
    assert rep.extra["movidos"] < movidos_cero


def test_no_muta_y_determinista():
    nueva, sol = _casos(50, 2)
    copia = dict(sol)
    r1 = reparar(nueva, sol, Backtracking(), LIM)
    r2 = reparar(nueva, sol, Backtracking(), LIM)
    assert sol == copia
    assert r1.asignacion == r2.asignacion
    assert r1.extra == r2.extra


def _instancia_radio():
    """T1 disponible solo en franjas 0-1 del día 0 y T2 en 0-2.

    Vigente: A (T1, g1) en f0, B (T2, g1) en f1, C (T2, g2) en f2.
    Nuevo: T1 solo tiene f1. A es inválido; liberar solo A deja a B en f1
    (único hueco de T1), así que A no cabe. Liberar vecinos (B) permite
    A en f1 y B en f0.
    """
    franjas = tuple(Franja(f"F{i}", 420 + 60 * i, 480 + 60 * i)
                    for i in range(3))
    todas = frozenset((0, h) for h in range(3))
    return Instancia(
        dias=(Dia(indice=0),),
        franjas=franjas,
        salones=(Salon("S1", capacidad=50),),
        docentes=(Docente("T1", disponibilidad=frozenset({(0, 1)})),
                  Docente("T2", disponibilidad=todas)),
        grupos=(Grupo("g1", 10, todas), Grupo("g2", 10, todas)),
        bloques=(Bloque("A", "m", 1, ("g1",), "T1"),
                 Bloque("B", "m", 1, ("g1",), "T2"),
                 Bloque("C", "m", 1, ("g2",), "T2")),
        nombre="radio")


def test_radio_libera_vecinos():
    inst = _instancia_radio()
    vigente = {"A": Posicion(0, 0, "S1"), "B": Posicion(0, 1, "S1"),
               "C": Posicion(0, 2, "S1")}
    assert bloques_invalidos(inst, vigente) == frozenset({"A"})
    res = reparar(inst, vigente, Backtracking(permitir_saltar=True), LIM)
    assert res.v == 0
    assert res.extra["radio"] >= 1
    assert res.extra["intentos"] >= 2
    assert res.asignacion["A"] == Posicion(0, 1, "S1")
    assert validar(inst, res.asignacion).violaciones.total == 0


# --- Sprint 5: la traza reproducida termina exactamente en el resultado ---

NOMBRES_SOLVER = ["backtracking", "a_estrella", "avara", "beam"]


def _inicial(instancia, vigente):
    """Estado de partida que usa la app: vigente menos inválidos."""
    inval = bloques_invalidos(instancia, vigente)
    return {b: p for b, p in vigente.items()
            if b in instancia.bloque and b not in inval}


def _caso_dificil(semilla):
    inst, sol = generar_instancia(30, 2, prob_disponible=0.1, prob_ventana=0.3)
    pert = perturbar_disponibilidad(inst, sol, semilla, num_docentes=2,
                                    fraccion=0.8)
    return pert, sol


@pytest.mark.parametrize("nombre", NOMBRES_SOLVER)
@pytest.mark.parametrize("semilla", range(6))
def test_traza_termina_en_resultado(nombre, semilla):
    from planificador.algoritmos.registro import crear_solver
    from planificador.algoritmos.reproduccion import lista_cuadros
    pert, sol = _caso_dificil(semilla)
    res = reparar(pert, sol, crear_solver(nombre),
                  Limites(max_nodos=2_000, max_segundos=3))
    cuadros = lista_cuadros(res.traza, _inicial(pert, sol))
    assert cuadros[-1].asignacion == res.asignacion
    assert res.traza.eventos[-1].tipo == "fin"


@pytest.mark.parametrize("fabrica", SOLVERS)
def test_traza_un_solo_intento(fabrica):
    from planificador.algoritmos.reproduccion import lista_cuadros
    d = mini_reparacion()
    inst, vigente = d["instancia"], d["solucion_vigente"]
    res = reparar(inst, vigente, fabrica(), LIM)
    assert res.extra["intentos"] == 1
    cuadros = lista_cuadros(res.traza, _inicial(inst, vigente))
    assert cuadros[-1].asignacion == res.asignacion


@pytest.mark.parametrize("nombre", NOMBRES_SOLVER)
def test_traza_truncada_conserva_sincronizacion(nombre):
    from planificador.algoritmos.registro import crear_solver
    from planificador.algoritmos.reproduccion import lista_cuadros
    pert, sol = _caso_dificil(0)
    res = reparar(pert, sol, crear_solver(nombre),
                  Limites(max_nodos=2_000, max_segundos=3,
                          max_eventos_traza=5))
    assert res.traza.truncada
    assert [e.tipo for e in res.traza.eventos[-2:]] == ["mejora", "fin"]
    cuadros = lista_cuadros(res.traza, _inicial(pert, sol))
    assert cuadros[-1].asignacion == res.asignacion
