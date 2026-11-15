"""Tests de la búsqueda informada: g, h, sucesores, A* y avara."""

import random
from dataclasses import replace

import pytest

from planificador.algoritmos.base import Limites
from planificador.algoritmos.comun import dominio_consistente
from planificador.algoritmos.informada import (
    AEstrella, Avara, Contexto, costo_camino, delta_g, heuristica,
    sucesores)
from planificador.core.estado import Estado
from planificador.core.validador import validar
from planificador.io_datos.sintetico import generar_instancia
from tests.fixtures.instancias_mini import (
    mini_factible, mini_infactible, mini_reparacion, mini_virtual)

SOLVERS = [AEstrella, Avara]


def _pequena(semilla, n=6, con_carga=True):
    inst, _ = generar_instancia(n, semilla, num_dias=2, num_franjas=4,
                                duracion_max=2, prob_virtual=0.0)
    if con_carga:  # activa el término de carga con topes bajos
        inst = replace(
            inst,
            docentes=tuple(replace(d, max_franjas_dia=2)
                           for d in inst.docentes),
            grupos=tuple(replace(g, max_franjas_dia=2) for g in inst.grupos))
    return inst


def _camino_aleatorio(ctx, rng, saltar_prob=0.15):
    """Baja por el árbol con decisiones aleatorias; devuelve la lista de nodos."""
    nodo = ctx.raiz()
    camino = [nodo]
    while not ctx.es_hoja(nodo):
        hijos = sucesores(ctx, nodo)
        elegible = hijos[:-1] if hijos[:-1] and rng.random() > saltar_prob \
            else hijos
        nodo = rng.choice(elegible)
        camino.append(nodo)
    return camino


# --------------------------------------------------------------------------
# g incremental
# --------------------------------------------------------------------------

@pytest.mark.parametrize("semilla", [1, 2, 3])
def test_g_incremental_igual_desde_cero(semilla):
    inst = _pequena(semilla, n=7)
    ctx = Contexto(inst)
    rng = random.Random(semilla)
    for _ in range(5):
        for nodo in _camino_aleatorio(ctx, rng):
            esperado = costo_camino(inst, ctx.asignacion_de(nodo),
                                    ctx.saltados_de(nodo))
            assert nodo.g == pytest.approx(esperado)


def test_g_monotono_y_delta_g_coincide():
    inst = _pequena(4, n=7)
    ctx = Contexto(inst)
    rng = random.Random(0)
    camino = _camino_aleatorio(ctx, rng)
    for padre, hijo in zip(camino, camino[1:]):
        assert hijo.g >= padre.g  # costo de paso >= 0
        est = ctx.estado_de(padre)
        assert hijo.g - padre.g == pytest.approx(
            delta_g(ctx, est, hijo.bloque, hijo.pos))


def test_g_no_cuenta_no_decididos():
    inst = mini_factible()["instancia"]
    ctx = Contexto(inst)
    assert ctx.raiz().g == 0.0
    assert costo_camino(inst, {}, ()) == 0.0


# --------------------------------------------------------------------------
# h admisible y consistente (óptimo restante por fuerza bruta)
# --------------------------------------------------------------------------

def _optimo_restante(ctx, nodo):
    """Mínimo de g sobre todas las hojas alcanzables desde ``nodo`` (fuerza
    bruta, orden fijo por id, g desde cero en cada hoja)."""
    inst = ctx.instancia
    asig = ctx.asignacion_de(nodo)
    saltados = set(ctx.saltados_de(nodo))
    pendientes = sorted(ctx.no_decididos_de(nodo))
    mejor = [float("inf")]

    def rec(i, est, salt):
        if i == len(pendientes):
            mejor[0] = min(mejor[0], costo_camino(
                inst, dict(est.asignacion), salt))
            return
        b = pendientes[i]
        for p in dominio_consistente(est, b):
            e2 = Estado(inst, {**est.asignacion, b: p})
            rec(i + 1, e2, salt)
        rec(i + 1, est, salt | {b})

    rec(0, Estado(inst, asig), saltados)
    return mejor[0]


@pytest.mark.parametrize("semilla", [1, 2, 3, 4])
def test_h_admisible_y_consistente_sinteticas(semilla):
    inst = _pequena(semilla, n=5)
    ctx = Contexto(inst)
    rng = random.Random(semilla)
    nodos = _camino_aleatorio(ctx, rng) + _camino_aleatorio(ctx, rng)
    for nodo in nodos:
        restante = _optimo_restante(ctx, nodo) - nodo.g
        est = ctx.estado_de(nodo)
        h_exacta = heuristica(est, ctx.no_decididos_de(nodo))
        assert nodo.h <= restante + 1e-9
        assert h_exacta <= restante + 1e-9
        assert nodo.h <= h_exacta + 1e-9  # la incremental es más débil
        for hijo in sucesores(ctx, nodo, est):  # consistencia
            assert nodo.h <= (hijo.g - nodo.g) + hijo.h + 1e-9


@pytest.mark.parametrize("fabrica", [mini_factible, mini_reparacion,
                                     mini_infactible, mini_virtual])
def test_h_admisible_mini(fabrica):
    inst = fabrica()["instancia"]
    ctx = Contexto(inst)
    raiz = ctx.raiz()
    assert raiz.h <= _optimo_restante(ctx, raiz) - raiz.g + 1e-9
    for hijo in sucesores(ctx, raiz):
        assert hijo.h <= _optimo_restante(ctx, hijo) - hijo.g + 1e-9


def test_h_cuenta_dominios_vacios():
    inst = mini_infactible()["instancia"]
    ctx = Contexto(inst)
    est = Estado(inst, {"B1": dominio_consistente(Estado(inst), "B1")[0]})
    assert heuristica(est, {"B2"}) == ctx.lam  # B2 sin posiciones consistentes


# --------------------------------------------------------------------------
# Optimalidad de A*
# --------------------------------------------------------------------------

@pytest.mark.parametrize("semilla", [1, 2, 3])
def test_a_estrella_g_minimo_fuerza_bruta(semilla):
    inst = _pequena(semilla, n=5)
    ctx = Contexto(inst)
    optimo = _optimo_restante(ctx, ctx.raiz())
    res = AEstrella().resolver(inst)
    assert res.terminado_por == "meta"
    assert res.extra["g"] == pytest.approx(optimo)
    assert costo_camino(inst, res.asignacion, ()) == pytest.approx(optimo)
    # la avara no es mejor que el óptimo
    assert Avara().resolver(inst).extra["g"] >= optimo - 1e-9


def test_a_estrella_ponderado_no_peor_que_cota():
    inst = _pequena(2, n=5)
    ctx = Contexto(inst)
    optimo = _optimo_restante(ctx, ctx.raiz())
    res = AEstrella(peso_h=2.0).resolver(inst)
    assert res.extra["g"] >= optimo - 1e-9


# --------------------------------------------------------------------------
# Comportamiento de los solvers
# --------------------------------------------------------------------------

@pytest.mark.parametrize("cls", SOLVERS)
@pytest.mark.parametrize("fabrica", [mini_factible, mini_reparacion,
                                     mini_virtual])
def test_mini_factibles_v0(cls, fabrica):
    inst = fabrica()["instancia"]
    res = cls().resolver(inst)
    assert res.v == 0 and res.terminado_por == "meta"
    assert validar(inst, res.asignacion).violaciones.total == 0
    assert any(e.tipo == "solucion" for e in res.traza.eventos)
    assert res.traza.eventos[-1].tipo == "fin"


@pytest.mark.parametrize("cls", SOLVERS)
def test_mini_infactible_v1(cls):
    inst = mini_infactible()["instancia"]
    res = cls().resolver(inst)
    assert res.v == 1 and res.extra["saltados"] == 1
    assert validar(inst, res.asignacion).violaciones.total == 1


@pytest.mark.parametrize("cls", SOLVERS)
@pytest.mark.parametrize("n", [20, 50])
def test_sinteticas_v0(cls, n):
    inst, _ = generar_instancia(n, 1)
    res = cls().resolver(inst, limites=Limites(max_segundos=20))
    assert res.v == 0, (res.terminado_por, res.nodos_expandidos)
    assert validar(inst, res.asignacion).violaciones.total == 0
    assert set(res.extra) >= {"saltados", "g", "h_inicial", "max_frontera"}


@pytest.mark.parametrize("n, semilla", [(50, 1), (50, 2), (50, 3),
                                        (100, 1)])
def test_avara_rapida_sin_agotar(n, semilla):
    """La avara con h de distancia se zambulle: no agota el tiempo.

    Si una semilla da v>0 debe ser por saltos legítimos (bloques sin
    dominio consistente), nunca por límite de tiempo.
    """
    inst, _ = generar_instancia(n, semilla)
    res = Avara().resolver(inst, limites=Limites(max_segundos=20))
    assert res.terminado_por == "meta"
    assert res.v == 0
    assert validar(inst, res.asignacion).violaciones.total == res.v


def test_avara_expande_menos_que_a_estrella():
    inst, _ = generar_instancia(50, 2)
    lim = Limites(max_segundos=10)
    av = Avara().resolver(inst, limites=lim)
    a = AEstrella().resolver(inst, limites=lim)
    assert av.nodos_expandidos < a.nodos_expandidos or (
        a.terminado_por != "meta")


@pytest.mark.parametrize("cls", SOLVERS)
def test_no_muta_estado_inicial_y_respeta_fijos(cls):
    datos = mini_reparacion()
    inst = datos["instancia"]
    fijo = {"B2": datos["solucion"]["B2"]}
    est = Estado(inst, fijo)
    antes = dict(est.asignacion)
    res = cls().resolver(inst, estado_inicial=est)
    assert dict(est.asignacion) == antes
    assert res.asignacion["B2"] == fijo["B2"]
    assert res.v == 0


@pytest.mark.parametrize("cls", SOLVERS)
def test_limite_nodos(cls):
    inst, _ = generar_instancia(20, 1)
    res = cls().resolver(inst, limites=Limites(max_nodos=3))
    assert res.terminado_por == "limite_nodos"
    assert res.nodos_expandidos == 3
    assert validar(inst, res.asignacion).problemas is not None
    assert res.v == len(inst.bloques) - len(res.asignacion)  # solo U cuenta


@pytest.mark.parametrize("cls", SOLVERS)
def test_determinismo(cls):
    inst, _ = generar_instancia(20, 2)
    a = cls().resolver(inst)
    b = cls().resolver(inst)
    assert a.asignacion == b.asignacion
    assert (a.nodos_expandidos, a.nodos_generados) == (
        b.nodos_expandidos, b.nodos_generados)


def test_traza_expandir_con_foto_y_repetidos():
    inst = mini_factible()["instancia"]
    res = AEstrella().resolver(inst)
    exp = [e for e in res.traza.eventos if e.tipo == "expandir"]
    assert exp and all(e.asignacion is not None for e in exp)
    assert exp[0].asignacion == ()
    # el espacio es un árbol: no hay estados repetidos que podar
    assert not any(e.tipo == "podar" for e in res.traza.eventos)
    sin_rep = AEstrella(detectar_repetidos=False).resolver(inst)
    assert sin_rep.asignacion == res.asignacion
