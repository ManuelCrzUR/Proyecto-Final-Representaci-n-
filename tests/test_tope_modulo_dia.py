"""C14: tope diario de franjas por serie/módulo (regla dura del motor)."""

import pytest

from planificador.algoritmos.backtracking import Backtracking
from planificador.algoritmos.base import Limites
from planificador.algoritmos.beam import BeamSearch
from planificador.algoritmos.informada import AEstrella, Avara
from planificador.algoritmos.reparacion import bloques_invalidos, reparar
from planificador.core import costo
from planificador.core.acciones import (
    aplicar_en_sitio, es_legal, posiciones_legales)
from planificador.core.estado import Estado
from planificador.core.modelo import (
    Anadir, Bloque, Dia, Docente, Franja, Grupo, Instancia, Intercambiar,
    Posicion, Reubicar, Salon)
from planificador.core.validador import validar

LIM = Limites(max_nodos=20_000, max_segundos=20.0)
DIAS, FR = 3, 6

SOLVERS = [
    pytest.param(lambda: Backtracking(), id="backtracking"),
    pytest.param(lambda: Backtracking(modo="optimizar"), id="bt_opt"),
    pytest.param(lambda: Backtracking(orden_valores="natural",
                                      forward_checking=False), id="bt_nofc"),
    pytest.param(lambda: AEstrella(), id="astar"),
    pytest.param(lambda: Avara(), id="avara"),
    pytest.param(lambda: BeamSearch(ancho=3), id="beam3"),
]


def _inst(n=6, tope=2, duracion=1, serie="M05|G1", otros=0):
    celdas = frozenset((d, h) for d in range(DIAS) for h in range(FR))
    bloques = [Bloque(f"B{i}", "M05", duracion, ("G1",), "T1",
                      serie=serie, max_franjas_dia=tope) for i in range(n)]
    bloques += [Bloque(f"X{i}", "M09", 1, ("G1",), "T1")
                for i in range(otros)]
    return Instancia(
        dias=tuple(Dia(d) for d in range(DIAS)),
        franjas=tuple(Franja(f"F{h}", 480 + 60 * h, 540 + 60 * h)
                      for h in range(FR)),
        salones=(Salon("S1"), Salon("S2")),
        docentes=(Docente("T1", disponibilidad=celdas),),
        grupos=(Grupo("G1", 10, celdas),),
        bloques=tuple(bloques))


def _por_dia(inst, asig, serie="M05|G1"):
    uso = {}
    for bid, p in asig.items():
        b = inst.bloque[bid]
        if b.serie == serie:
            uso[p.dia] = uso.get(p.dia, 0) + b.duracion
    return uso


def test_contador_incremental_y_copias():
    inst = _inst()
    e = Estado(inst)
    aplicar_en_sitio(e, Anadir("B0", Posicion(1, 0, "S1")))
    aplicar_en_sitio(e, Anadir("B1", Posicion(1, 3, "S1")))
    assert e.franjas_serie("M05|G1", 1) == 2
    c = e.copiar()
    inversa = aplicar_en_sitio(e, Reubicar("B1", Posicion(2, 0, "S1")))
    assert e.franjas_serie("M05|G1", 1) == 1
    assert e.franjas_serie("M05|G1", 2) == 1
    assert c.franjas_serie("M05|G1", 1) == 2
    aplicar_en_sitio(e, inversa)
    assert e.franjas_serie("M05|G1", 1) == 2
    assert e.franjas_serie("M05|G1", 2) == 0


def test_legalidad_tope():
    inst = _inst()
    e = Estado(inst)
    aplicar_en_sitio(e, Anadir("B0", Posicion(0, 0, "S1")))
    aplicar_en_sitio(e, Anadir("B1", Posicion(0, 1, "S1")))
    assert not es_legal(e, Anadir("B2", Posicion(0, 4, "S2")))
    assert es_legal(e, Anadir("B2", Posicion(1, 4, "S2")))
    assert all(p.dia != 0 for p in posiciones_legales(e, "B2"))
    # B1 puede moverse dentro del mismo día (se ignora a sí mismo).
    assert es_legal(e, Reubicar("B1", Posicion(0, 5, "S1")))
    with pytest.raises(ValueError):
        aplicar_en_sitio(e, Anadir("B2", Posicion(0, 4, "S1")))
    assert "B2" in e.sin_ubicar()


def test_intercambio_respeta_tope():
    inst = _inst(n=4)
    e = Estado(inst, {"B0": Posicion(0, 0, "S1"), "B1": Posicion(0, 1, "S1"),
                      "B2": Posicion(1, 0, "S1"), "B3": Posicion(1, 1, "S1")})
    assert es_legal(e, Intercambiar("B0", "B2"))


def test_duracion_mayor_que_tope_no_tiene_posiciones():
    inst = _inst(n=1, tope=1, duracion=2)
    assert posiciones_legales(Estado(inst), "B0") == []


@pytest.mark.parametrize("fabrica", SOLVERS)
def test_solver_respeta_tope(fabrica):
    inst = _inst(n=6, tope=2, otros=2)
    res = fabrica().resolver(inst, limites=LIM)
    assert res.v == 0
    assert max(_por_dia(inst, res.asignacion).values()) <= 2
    rep = validar(inst, res.asignacion)
    assert rep.violaciones.modulo_dia == 0 and rep.violaciones.total == 0


@pytest.mark.parametrize("fabrica", SOLVERS)
def test_infactible_por_tope_termina(fabrica):
    inst = _inst(n=7, tope=2)  # 3 dias x 2 = 6 < 7
    res = fabrica().resolver(inst, limites=Limites(max_nodos=5_000,
                                                   max_segundos=10.0))
    assert res.v > 0
    assert res.violaciones.modulo_dia == 0
    assert max(_por_dia(inst, res.asignacion).values()) <= 2
    assert len(res.asignacion) <= 6


@pytest.mark.parametrize("fabrica", SOLVERS)
def test_reparar_respeta_tope(fabrica):
    inst = _inst(n=6, tope=2)
    # Vigente con 3 bloques el día 0 (excede el tope) y 3 sueltos.
    vigente = {"B0": Posicion(0, 0, "S1"), "B1": Posicion(0, 1, "S1"),
               "B2": Posicion(0, 2, "S1"), "B3": Posicion(1, 0, "S1"),
               "B4": Posicion(1, 1, "S1"), "B5": Posicion(2, 0, "S1")}
    assert bloques_invalidos(inst, vigente) == frozenset({"B2"})
    res = reparar(inst, vigente, fabrica(), LIM)
    assert res.v == 0
    assert max(_por_dia(inst, res.asignacion).values()) <= 2
    assert validar(inst, res.asignacion).violaciones.total == 0


def test_validar_cuenta_modulo_dia():
    inst = _inst(n=5, tope=2)
    asig = {f"B{i}": Posicion(2, i, "S1") for i in range(5)}
    rep = validar(inst, asig)
    assert rep.violaciones.modulo_dia == 3
    assert rep.violaciones.total == 3
    assert ("El módulo M05 tiene 5 franjas el día 2 (máximo 2)"
            in rep.problemas)
    # El costo del core coincide con el oráculo.
    assert costo.violaciones(Estado(inst, asig)).modulo_dia == 3
    assert abs(costo.F(Estado(inst, asig)) - rep.F) < 1e-9


def test_sin_topes_sin_efecto():
    base = _inst(n=6, tope=None, serie=None, otros=2)
    con_serie = _inst(n=6, tope=None, serie="M05|G1", otros=2)
    for fab in (lambda: Backtracking(), lambda: AEstrella(),
                lambda: BeamSearch(ancho=3)):
        a = fab().resolver(base, limites=LIM)
        b = fab().resolver(con_serie, limites=LIM)
        assert a.asignacion == b.asignacion
        assert (a.F, a.nodos_expandidos, a.nodos_generados) == (
            b.F, b.nodos_expandidos, b.nodos_generados)
