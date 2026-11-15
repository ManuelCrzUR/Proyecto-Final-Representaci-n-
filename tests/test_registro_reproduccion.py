"""Tests del registro de solvers y de la reproducción de trazas."""

import pytest

from planificador.algoritmos.base import Limites
from planificador.algoritmos.registro import NOMBRES, REGISTRO, crear_solver
from planificador.algoritmos.reproduccion import cuadros_de_resultado, lista_cuadros
from planificador.io_datos.sintetico import generar_instancia
from tests.fixtures.instancias_mini import mini_factible


def test_registro_completo():
    assert set(NOMBRES) == {"backtracking", "a_estrella", "avara", "beam"}
    for nombre in NOMBRES:
        s = crear_solver(nombre)
        assert s.nombre == nombre
        assert REGISTRO[nombre].descripcion


def test_parametros_sobrescriben():
    assert crear_solver("beam", ancho=3).parametros["ancho"] == 3
    with pytest.raises(KeyError):
        crear_solver("inexistente")


@pytest.mark.parametrize("nombre", NOMBRES)
def test_ultimo_cuadro_es_la_solucion(nombre):
    """Reproducir la traza termina exactamente en el resultado."""
    inst = mini_factible()["instancia"]
    res = crear_solver(nombre).resolver(inst, limites=Limites(max_segundos=10))
    cs = cuadros_de_resultado(res)
    assert cs and cs[-1].asignacion == res.asignacion


@pytest.mark.parametrize("nombre", ["backtracking", "avara", "beam"])
def test_reproduccion_sintetica(nombre):
    inst, _ = generar_instancia(20, semilla=1)
    params = {"ancho": 3} if nombre == "beam" else {}
    res = crear_solver(nombre, **params).resolver(
        inst, limites=Limites(max_segundos=20))
    assert not res.traza.truncada
    assert cuadros_de_resultado(res)[-1].asignacion == res.asignacion


def test_muestreo_conserva_extremos():
    inst, _ = generar_instancia(20, semilla=1)
    res = crear_solver("backtracking").resolver(inst)
    todos = lista_cuadros(res.traza)
    pocos = lista_cuadros(res.traza, max_cuadros=5)
    assert len(pocos) <= 5
    assert pocos[0].indice == todos[0].indice
    assert pocos[-1].asignacion == todos[-1].asignacion
