"""Tests de humo cruzados: todos los solvers sobre todas las fixtures mini.

Cada combinación (solver, fixture) comprueba el contrato común de
``docs/contrato.md`` (Sprint 3): resultado bien formado, coincidencia con el
oráculo ``validar``, v = 0 en instancias factibles, traza terminada en ``fin``,
determinismo y no mutación del ``estado_inicial``.
"""

import pytest

from planificador.algoritmos.backtracking import Backtracking
from planificador.algoritmos.base import Limites, Resultado
from planificador.algoritmos.beam import BeamSearch
from planificador.algoritmos.informada import AEstrella, Avara
from planificador.core.estado import Estado
from planificador.core.modelo import Posicion
from planificador.core.validador import validar
from tests.fixtures.instancias_mini import TODAS_LAS_FIXTURES, mini_factible

SOLVERS = [
    pytest.param(lambda: Backtracking(), id="backtracking"),
    pytest.param(lambda: Backtracking(modo="optimizar"),
                 id="backtracking-optimizar"),
    pytest.param(lambda: AEstrella(), id="a_estrella"),
    pytest.param(lambda: Avara(), id="avara"),
    pytest.param(lambda: BeamSearch(ancho=3), id="beam-ancho3"),
]

FIXTURES = [pytest.param(fn, id=fn.__name__) for fn in TODAS_LAS_FIXTURES]

TERMINACIONES = {"meta", "agotado", "limite_nodos", "limite_tiempo"}

# Fixtures con v exacto: el bloque que no tiene dominio se salta y cuesta 1.
V_EXACTO = {"mini_infactible": 1, "mini_sin_disponibilidad": 1}

LIMITES = Limites(max_segundos=10)


@pytest.mark.parametrize("fabrica", SOLVERS)
@pytest.mark.parametrize("fx_fn", FIXTURES)
def test_resultado_bien_formado(fabrica, fx_fn):
    solver = fabrica()
    fx = fx_fn()
    res = solver.resolver(fx["instancia"], limites=LIMITES)
    assert isinstance(res, Resultado)
    assert res.algoritmo.startswith(solver.nombre)
    assert res.terminado_por in TERMINACIONES


@pytest.mark.parametrize("fabrica", SOLVERS)
@pytest.mark.parametrize("fx_fn", FIXTURES)
def test_coincide_con_oraculo(fabrica, fx_fn):
    fx = fx_fn()
    inst = fx["instancia"]
    res = fabrica().resolver(inst, limites=LIMITES)
    reporte = validar(inst, res.asignacion)
    assert reporte.violaciones == res.violaciones
    assert res.F == pytest.approx(reporte.F)


@pytest.mark.parametrize("fabrica", SOLVERS)
@pytest.mark.parametrize("fx_fn", FIXTURES)
def test_sin_violaciones_de_salon(fabrica, fx_fn):
    fx = fx_fn()
    res = fabrica().resolver(fx["instancia"], limites=LIMITES)
    assert res.violaciones.salon == 0


@pytest.mark.parametrize("fabrica", SOLVERS)
@pytest.mark.parametrize("fx_fn", FIXTURES)
def test_factible_da_v_cero(fabrica, fx_fn):
    fx = fx_fn()
    if not fx["factible"]:
        pytest.skip("la fixture no es factible")
    res = fabrica().resolver(fx["instancia"], limites=LIMITES)
    assert res.v == 0


@pytest.mark.parametrize("fabrica", SOLVERS)
@pytest.mark.parametrize("fx_fn", FIXTURES)
def test_v_minimo(fabrica, fx_fn):
    fx = fx_fn()
    if "v_minimo" not in fx:
        pytest.skip("la fixture no declara v_minimo")
    res = fabrica().resolver(fx["instancia"], limites=LIMITES)
    assert res.v >= 1
    nombre = fx["instancia"].nombre
    if nombre in V_EXACTO:
        assert res.v == V_EXACTO[nombre]


@pytest.mark.parametrize("fabrica", SOLVERS)
@pytest.mark.parametrize("fx_fn", FIXTURES)
def test_traza_termina_en_fin(fabrica, fx_fn):
    fx = fx_fn()
    res = fabrica().resolver(fx["instancia"], limites=LIMITES)
    eventos = res.traza.eventos
    assert eventos
    assert eventos[-1].tipo == "fin"
    assert eventos[-1].nota == res.terminado_por


@pytest.mark.parametrize("fabrica", SOLVERS)
@pytest.mark.parametrize("fx_fn", FIXTURES)
def test_determinismo(fabrica, fx_fn):
    inst = fx_fn()["instancia"]
    primera = fabrica().resolver(inst, limites=LIMITES)
    segunda = fabrica().resolver(inst, limites=LIMITES)
    assert primera.asignacion == segunda.asignacion


@pytest.mark.parametrize("fabrica", SOLVERS)
def test_no_muta_estado_inicial(fabrica):
    inst = mini_factible()["instancia"]
    fijo = Posicion(1, 0, "S1")
    estado = Estado(inst, {"B2": fijo})
    antes = dict(estado.asignacion)
    sin_ubicar_antes = set(estado.sin_ubicar())

    res = fabrica().resolver(inst, estado_inicial=estado, limites=LIMITES)

    assert dict(estado.asignacion) == antes
    assert set(estado.sin_ubicar()) == sin_ubicar_antes
    assert res.asignacion["B2"] == fijo
