"""Integración del core (compuerta 2): fixtures, estado/acciones, costo, validador."""

import random

import pytest

from planificador.core import costo
from planificador.core.acciones import (
    acciones_legales, aplicar_en_sitio, es_legal, posiciones_legales)
from planificador.core.estado import Estado
from planificador.core.modelo import Anadir, Eliminar
from planificador.core.validador import validar
from tests.fixtures.instancias_mini import TODAS_LAS_FIXTURES


@pytest.mark.parametrize("fabrica", TODAS_LAS_FIXTURES)
def test_solucion_conocida_tiene_v_esperado(fabrica):
    fx = fabrica()
    if fx["solucion"] is None:
        pytest.skip("sin solución conocida")
    estado = Estado(fx["instancia"], fx["solucion"])
    assert costo.v(estado) == fx["v_esperado_solucion"]
    rep = validar(fx["instancia"], fx["solucion"])
    assert rep.violaciones == costo.violaciones(estado)
    assert rep.F == pytest.approx(costo.F(estado))


def test_reparacion_vigente_tiene_v_3():
    from tests.fixtures.instancias_mini import mini_reparacion
    fx = mini_reparacion()
    estado = Estado(fx["instancia"], fx["solucion_vigente"])
    viol = costo.violaciones(estado)
    assert viol.total == fx["v_esperado_vigente"] == viol.disponibilidad


def test_virtual_posicion_ilegal():
    from tests.fixtures.instancias_mini import mini_virtual
    fx = mini_virtual()
    bloque, pos = fx["posicion_ilegal"]
    assert not es_legal(Estado(fx["instancia"]), Anadir(bloque, pos))


def _completos_alcanzables(instancia):
    """Enumera por fuerza bruta todos los estados alcanzables con 'añadir' legal."""
    vistos, pila, finales = set(), [Estado(instancia)], []
    while pila:
        e = pila.pop()
        if e.clave() in vistos:
            continue
        vistos.add(e.clave())
        hijos = [a for a in acciones_legales(e) if isinstance(a, Anadir)]
        if not hijos:
            finales.append(e)
        for a in hijos:
            h = e.copiar()
            aplicar_en_sitio(h, a)
            pila.append(h)
    return finales


@pytest.mark.parametrize("nombre", ["mini_infactible", "mini_sin_disponibilidad"])
def test_infactibles_siempre_v_positivo(nombre):
    from tests.fixtures import instancias_mini
    fx = getattr(instancias_mini, nombre)()
    finales = _completos_alcanzables(fx["instancia"])
    assert finales
    assert min(costo.v(e) for e in finales) == fx["v_min_solo_anadir"]


@pytest.mark.parametrize("fabrica", TODAS_LAS_FIXTURES)
def test_paseo_aleatorio_F_coincide_con_validador(fabrica):
    """Acciones legales aleatorias: F del core == F del validador; deshacer restaura."""
    inst = fabrica()["instancia"]
    rng = random.Random(7)
    estado = Estado(inst)
    for _ in range(200):
        acciones = list(acciones_legales(estado))
        if not acciones:
            break
        accion = rng.choice(acciones)
        antes = estado.clave()
        F_antes = costo.F(estado)
        inversa = aplicar_en_sitio(estado, accion)
        rep = validar(inst, dict(estado.asignacion))
        assert rep.F == pytest.approx(costo.F(estado))
        assert rep.violaciones.salon == 0  # las acciones legales nunca violan salón
        if rng.random() < 0.3:
            aplicar_en_sitio(estado, inversa)
            assert estado.clave() == antes
            assert costo.F(estado) == pytest.approx(F_antes)


def test_anadir_eliminar_restaura():
    from tests.fixtures.instancias_mini import mini_factible
    inst = mini_factible()["instancia"]
    e = Estado(inst)
    clave0 = e.clave()
    pos = posiciones_legales(e, "B1")[0]
    aplicar_en_sitio(e, Anadir("B1", pos))
    aplicar_en_sitio(e, Eliminar("B1"))
    assert e.clave() == clave0
    assert e.sin_ubicar() == frozenset(b.id for b in inst.bloques)


def test_a_dict_es_json_serializable():
    import json

    from planificador.core.modelo import Instancia
    from planificador.io_datos.sintetico import generar_instancia
    inst, _ = generar_instancia(50, semilla=3)
    texto = json.dumps(inst.a_dict())
    assert Instancia.desde_dict(json.loads(texto)) == inst
