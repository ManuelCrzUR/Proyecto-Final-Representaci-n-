"""Tests del validador independiente frente a costo.py."""

import math
import random

import pytest

from planificador.core import costo
from planificador.core.modelo import (
    Bloque, Dia, Docente, Franja, Grupo, Instancia, Pesos, Posicion, Salon)
from planificador.core.validador import Reporte, validar
from tests.test_costo import ESCENARIOS, estado

CLAVES = ("hueco_docente", "hueco_grupo", "dispersion_docente",
          "carga_grupo", "hora_extrema", "cambio_sede")


def comparar(inst, asig):
    rep = validar(inst, asig)
    est = estado(inst, asig)
    assert rep.violaciones == costo._violaciones_de(inst, asig)
    assert rep.violaciones == costo.violaciones(est)
    assert rep.f == pytest.approx(costo.f(est), abs=1e-9)
    assert rep.F == pytest.approx(costo.F(est), abs=1e-9)
    return rep


@pytest.mark.parametrize("nombre", sorted(ESCENARIOS))
def test_escenarios_igual_que_costo(nombre):
    inst, asig = ESCENARIOS[nombre]()
    comparar(inst, asig)


def test_reporte_inmutable_y_tipos():
    inst, asig = ESCENARIOS["mixto"]()
    rep = validar(inst, asig)
    assert isinstance(rep, Reporte)
    with pytest.raises(Exception):
        rep.f = 3.0
    assert rep.f == pytest.approx(11.0)
    assert rep.F == pytest.approx(111.0)
    assert rep.violaciones.total == 1


def test_lam_automatico_en_F():
    inst, asig = ESCENARIOS["mixto"]()
    auto = Instancia(inst.dias, inst.franjas, inst.salones, inst.docentes,
                     inst.grupos, inst.bloques,
                     Pesos(hueco_docente=1.5, hora_extrema=4.0))
    assert validar(auto, asig).F == pytest.approx(11 + 92)


def texto(nombre):
    inst, asig = ESCENARIOS[nombre]()
    return "\n".join(validar(inst, asig).problemas)


def test_mensaje_sin_ubicar():
    assert "Bloque B2 sin ubicar" in texto("sin_ubicar")


def test_mensaje_disponibilidad():
    assert ("Bloque B1: docente T1 no disponible el día 0, franja 2"
            in texto("disponibilidad"))


def test_mensaje_ventana():
    assert ("Bloque B1: grupo G1 fuera de su ventana el día 1, franja 1"
            in texto("ventana_dos_grupos"))


def test_mensaje_conflicto_docente_y_grupo():
    assert ("Bloques B1 y B2 se cruzan (docente T1) el día 0 franja 1"
            in texto("conflicto_docente"))
    assert ("Bloques B1 y B2 se cruzan (grupo G1) el día 0 franja 1"
            in texto("conflicto_grupo"))


def test_mensaje_choque_de_salon():
    assert ("Bloques B1, B2, B3 comparten el salón S1 el día 0 franja 1"
            in texto("salon_choque"))


def test_mensajes_salon_invalido():
    t = texto("salon_invalido")
    assert "Bloque B1: el salón S1 (capacidad 30) no alberga 40" in t
    assert "Bloque B2: requiere salón de tipo LAB" in t
    assert "Bloque B3: bloque virtual en el salón presencial S2" in t
    assert "Bloque B4: bloque presencial en el salón virtual V" in t
    assert "Bloque B5: el salón XX no existe" in t
    assert "B6:" not in t


def test_mensaje_fuera_de_rango():
    t = texto("fuera_de_rango")
    assert "Bloque B1: posición fuera de rango" in t
    assert "Bloque B2: posición fuera de rango" in t


def test_sin_problemas_en_asignacion_limpia():
    inst, asig = ESCENARIOS["virtual_simultaneo"]()
    assert validar(inst, asig).problemas == []


# --------------------------------------------------------------------------
# Test aleatorio
# --------------------------------------------------------------------------

def instancia_mediana(rng):
    D, H = 5, 6
    franjas = tuple(Franja(f"F{h}", 420 + 60 * h, 480 + 60 * h,
                           extrema=h in (0, H - 1)) for h in range(H))
    celdas = [(d, h) for d in range(D) for h in range(H)]
    salones = [Salon(f"S{i}", rng.choice(["AULA", "LAB"]),
                     rng.choice([15, 25, 40]), False, rng.choice("AB"))
               for i in range(6)]
    salones.append(Salon("V1", "VIRTUAL", None, True, ""))
    salones.append(Salon("V2", "VIRTUAL", None, True, ""))
    docentes = tuple(
        Docente(f"T{i}", disponibilidad=frozenset(
            c for c in celdas if rng.random() < 0.7),
            max_franjas_dia=rng.choice([None, 2, 3]))
        for i in range(6))
    grupos = tuple(
        Grupo(f"G{i}", rng.choice([10, 20, 30]), frozenset(
            c for c in celdas if rng.random() < 0.8),
            max_franjas_dia=rng.choice([None, 2, 4]))
        for i in range(8))
    bloques = []
    for i in range(40):
        bloques.append(Bloque(
            f"B{i}", f"M{i}", rng.choice([1, 1, 2, 3]),
            tuple(rng.sample([g.id for g in grupos], rng.choice([1, 1, 2]))),
            rng.choice([None] + [d.id for d in docentes]),
            tipo_salon=rng.choice([None, None, "AULA", "LAB"]),
            virtual=rng.random() < 0.2))
    pesos = Pesos(1.0, 2.0, 0.5, 3.0, 1.5, 2.5,
                  lam=rng.choice([None, 50.0]))
    return Instancia(tuple(Dia(i) for i in range(D)), franjas,
                     tuple(salones), docentes, grupos, tuple(bloques),
                     pesos)


def asignacion_aleatoria(rng, inst):
    ids_salon = [s.id for s in inst.salones]
    asig = {}
    for b in inst.bloques:
        if rng.random() < 0.15:
            continue
        r = rng.random()
        if r < 0.03:
            pos = Posicion(rng.randint(-1, inst.num_dias + 1),
                           rng.randint(-1, inst.num_franjas + 1),
                           rng.choice(ids_salon))
        elif r < 0.05:
            pos = Posicion(rng.randrange(inst.num_dias),
                           rng.randrange(inst.num_franjas), "NOEXISTE")
        else:
            pos = Posicion(rng.randrange(inst.num_dias),
                           rng.randrange(inst.num_franjas - b.duracion + 1),
                           rng.choice(ids_salon))
        asig[b.id] = pos
    return asig


def test_aleatorio_coincide_con_costo():
    rng = random.Random(20240607)
    inst = instancia_mediana(rng)
    for _ in range(300):
        asig = asignacion_aleatoria(rng, inst)
        rep = validar(inst, asig)
        assert rep.violaciones == costo._violaciones_de(inst, asig)
        assert abs(rep.f - costo._f_de(inst, asig)) < 1e-9
        est = estado(inst, asig)
        assert abs(rep.F - costo.F(est)) < 1e-9
        assert math.isclose(rep.f, costo.f(est), abs_tol=1e-9)
        assert rep.f <= costo.cota_superior_f(inst) + 1e-9
