"""Pruebas del generador de instancias sintéticas."""

import time

import pytest

from planificador.core import validador
from planificador.core.acciones import es_legal
from planificador.core.costo import v
from planificador.core.estado import Estado
from planificador.core.modelo import Anadir
from planificador.io_datos.sintetico import (
    cargar_json, generar_instancia, guardar_json, main,
    perturbar_disponibilidad)

TAMANOS = (20, 50, 100, 200)


def test_determinismo():
    a, sa = generar_instancia(30, 7)
    b, sb = generar_instancia(30, 7)
    assert a == b and a.a_dict() == b.a_dict() and sa == sb


def test_semillas_distintas():
    a, _ = generar_instancia(30, 1)
    b, _ = generar_instancia(30, 2)
    assert a.a_dict() != b.a_dict()


@pytest.mark.parametrize("n", TAMANOS)
def test_solucion_oculta_valida(n):
    t0 = time.perf_counter()
    inst, sol = generar_instancia(n, 11)
    assert time.perf_counter() - t0 < 5
    assert len(inst.bloques) == n
    assert set(sol) == {b.id for b in inst.bloques}
    assert validador.validar(inst, sol).violaciones.total == 0
    assert v(Estado(inst, sol)) == 0


@pytest.mark.parametrize("n", (20, 50))
def test_posiciones_legales(n):
    inst, sol = generar_instancia(n, 3)
    for bid, pos in sol.items():
        est = Estado(inst, {k: p for k, p in sol.items() if k != bid})
        assert es_legal(est, Anadir(bid, pos))


@pytest.mark.parametrize("n", (20, 100))
def test_salon_compatible(n):
    inst, _ = generar_instancia(n, 5)
    for b in inst.bloques:
        if b.virtual:
            assert any(s.virtual for s in inst.salones)
            continue
        e = inst.estudiantes(b.id)
        assert any(not s.virtual
                   and (b.tipo_salon is None or b.tipo_salon == s.tipo)
                   and s.capacidad >= e for s in inst.salones)


def test_perturbar():
    inst, sol = generar_instancia(50, 4)
    pert = perturbar_disponibilidad(inst, sol, 9, num_docentes=2)
    assert pert.nombre == f"{inst.nombre}-perturbada"
    assert v(Estado(pert, sol)) > 0
    cambiados = [d.id for d, p in zip(inst.docentes, pert.docentes)
                 if d != p]
    assert len(cambiados) == 2
    assert pert.grupos == inst.grupos and pert.bloques == inst.bloques
    assert pert.salones == inst.salones


def test_json_ida_vuelta(tmp_path):
    inst, sol = generar_instancia(20, 2)
    ruta = tmp_path / "x" / "i.json"
    guardar_json(inst, ruta, sol)
    inst2, sol2 = cargar_json(ruta)
    assert inst2 == inst and sol2 == sol
    guardar_json(inst, ruta)
    assert cargar_json(ruta)[1] is None


def test_no_factible():
    inst, sol = generar_instancia(30, 1, garantizar_factible=False)
    assert sol is None
    assert len(inst.bloques) == 30
    Estado(inst)


def test_cli(tmp_path, capsys):
    ruta = tmp_path / "s.json"
    assert main(["--bloques", "20", "--semilla", "1",
                 "--salida", str(ruta)]) == 0
    assert ruta.exists()
    assert "20 bloques" in capsys.readouterr().out
