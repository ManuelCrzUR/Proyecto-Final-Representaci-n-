"""Tests del contrato de algoritmos (base.py) y utilidades comunes (comun.py)."""

import pytest

from planificador.algoritmos.base import Limites, Presupuesto, Traza, foto
from planificador.algoritmos.comun import (
    consistente, dominio_consistente, dominio_unario, elegir_mrv)
from planificador.core.acciones import aplicar_en_sitio
from planificador.core.conflictos import construir_conflictos
from planificador.core.estado import Estado
from planificador.core.modelo import Anadir, Posicion
from tests.fixtures.instancias_mini import mini_factible, mini_reparacion


def test_traza_tope_y_tipos():
    t = Traza(max_eventos=2)
    t.registrar("add", bloque="B1")
    t.registrar("del", bloque="B1")
    t.registrar("add", bloque="B2")
    t.registrar("fin", nota="meta")  # "fin" siempre se registra
    assert [e.tipo for e in t.eventos] == ["add", "del", "fin"]
    assert t.truncada and t.descartados == 1
    with pytest.raises(ValueError):
        t.registrar("inventado")


def test_presupuesto_limite_nodos():
    p = Presupuesto(Limites(max_nodos=3, max_segundos=None))
    assert p.agotado() is None
    p.nodos_expandidos = 3
    assert p.agotado() == "limite_nodos"


def test_foto_ordenada():
    assert foto({"B2": Posicion(0, 0, "S"), "B1": Posicion(1, 0, "S")})[0][0] == "B1"


def test_dominio_unario_respeta_disponibilidad():
    inst = mini_reparacion()["instancia"]  # T1 solo disponible el día 1
    dom = dominio_unario(Estado(inst), "B1")
    assert dom and all(p.dia == 1 for p in dom)


def test_dominio_consistente_y_mrv():
    inst = mini_factible()["instancia"]
    e = Estado(inst)
    aplicar_en_sitio(e, Anadir("B1", Posicion(0, 0, "S1")))  # T1, G1 en F1-F2 día 0
    # B3 (T1) no puede ir el día 0 en F1/F2.
    assert not consistente(e, "B3", Posicion(0, 0, "S2"))
    dom3 = dominio_consistente(e, "B3")
    assert Posicion(0, 2, "S2") in dom3
    assert all(not (p.dia == 0 and p.franja < 2) for p in dom3)
    doms = {b: dominio_consistente(e, b) for b in ("B2", "B3")}
    elegido = elegir_mrv(doms, construir_conflictos(inst))
    assert len(doms[elegido]) == min(len(d) for d in doms.values())


def test_dominio_unario_con_cache_equivale_a_la_definicion():
    """La caché del dominio base da lo mismo que filtrar posiciones_legales."""
    import random

    from planificador.algoritmos.comun import _respeta_unarias, dominio_unario
    from planificador.core.acciones import posiciones_legales
    from planificador.io_datos.sintetico import generar_instancia

    inst, sol = generar_instancia(30, 3, prob_disponible=0.4)
    rng = random.Random(0)
    for _ in range(5):
        elegidos = rng.sample(sorted(sol), 15)
        est = Estado(inst, {b: sol[b] for b in elegidos})
        for b in inst.bloques:
            esperado = [p for p in posiciones_legales(est, b.id)
                        if _respeta_unarias(inst, b, p)]
            assert dominio_unario(est, b.id) == esperado
