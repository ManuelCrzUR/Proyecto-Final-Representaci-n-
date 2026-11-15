"""Pruebas de las instancias mini: forma, ida y vuelta, y verificación a mano."""

from itertools import combinations

import pytest

from planificador.core.modelo import Instancia, celdas_de
from tests.fixtures.instancias_mini import (
    TODAS_LAS_FIXTURES,
    mini_factible,
    mini_reparacion,
)

CLAVES_OBLIGATORIAS = {
    "instancia",
    "descripcion",
    "factible",
    "solucion",
    "v_esperado_solucion",
}


def _asignaciones(datos):
    """Yield (nombre, asignación) para cada solución presente en la fixture."""
    for nombre in ("solucion", "solucion_vigente"):
        asignacion = datos.get(nombre)
        if asignacion is not None:
            yield nombre, asignacion


def _celdas_por_bloque(inst, asignacion):
    """Mapa bloque -> conjunto de celdas (dia, franja) que ocupa."""
    return {
        bid: set(celdas_de(pos, inst.bloque[bid].duracion))
        for bid, pos in asignacion.items()
    }


def _verificar_sin_choques(inst, asignacion):
    """Ningún par de bloques con docente o grupo común comparte celda."""
    celdas = _celdas_por_bloque(inst, asignacion)
    for a, b in combinations(sorted(asignacion), 2):
        ba, bb = inst.bloque[a], inst.bloque[b]
        mismo_docente = ba.docente_id is not None and (
            ba.docente_id == bb.docente_id
        )
        mismo_grupo = bool(set(ba.grupos) & set(bb.grupos))
        if mismo_docente or mismo_grupo:
            assert not (celdas[a] & celdas[b]), f"Choque entre {a} y {b}"


def _verificar_disponibilidad_y_ventana(inst, asignacion):
    """Cada celda de cada bloque está en la disponibilidad y en la ventana."""
    for bid, pos in asignacion.items():
        bloque = inst.bloque[bid]
        for celda in celdas_de(pos, bloque.duracion):
            disp = inst.docente[bloque.docente_id].disponibilidad
            assert celda in disp, f"{bid} fuera de disponibilidad en {celda}"
            for gid in bloque.grupos:
                ventana = inst.grupo[gid].ventana
                assert celda in ventana, f"{bid} fuera de ventana de {gid}"


def _celdas_fuera_disponibilidad(inst, asignacion):
    """Cuenta las celdas ocupadas por bloques que el docente no tiene libres."""
    total = 0
    for bid, pos in asignacion.items():
        bloque = inst.bloque[bid]
        disp = inst.docente[bloque.docente_id].disponibilidad
        total += sum(
            1 for celda in celdas_de(pos, bloque.duracion) if celda not in disp
        )
    return total


@pytest.mark.parametrize("fabrica", TODAS_LAS_FIXTURES, ids=lambda f: f.__name__)
def test_forma_del_dict(fabrica):
    datos = fabrica()
    assert CLAVES_OBLIGATORIAS <= datos.keys()
    assert isinstance(datos["instancia"], Instancia)
    assert isinstance(datos["descripcion"], str)
    assert isinstance(datos["factible"], bool)


@pytest.mark.parametrize("fabrica", TODAS_LAS_FIXTURES, ids=lambda f: f.__name__)
def test_soluciones_bien_formadas(fabrica):
    datos = fabrica()
    inst = datos["instancia"]
    for nombre, asignacion in _asignaciones(datos):
        for bid, pos in asignacion.items():
            assert bid in inst.bloque, f"{nombre}: bloque {bid} inexistente"
            bloque = inst.bloque[bid]
            assert 0 <= pos.dia < inst.num_dias, f"{nombre}: día fuera de rango"
            assert pos.franja + bloque.duracion <= inst.num_franjas, (
                f"{nombre}: {bid} se sale de las franjas"
            )
            assert pos.salon in inst.salon, f"{nombre}: salón {pos.salon} inexistente"


@pytest.mark.parametrize("fabrica", TODAS_LAS_FIXTURES, ids=lambda f: f.__name__)
def test_ida_y_vuelta_serializacion(fabrica):
    inst = fabrica()["instancia"]
    assert Instancia.desde_dict(inst.a_dict()) == inst


def test_mini_factible_a_mano():
    datos = mini_factible()
    inst = datos["instancia"]
    asignacion = datos["solucion"]
    _verificar_sin_choques(inst, asignacion)
    _verificar_disponibilidad_y_ventana(inst, asignacion)


def test_mini_reparacion_solucion_reparada_a_mano():
    datos = mini_reparacion()
    inst = datos["instancia"]
    asignacion = datos["solucion"]
    _verificar_sin_choques(inst, asignacion)
    _verificar_disponibilidad_y_ventana(inst, asignacion)


def test_mini_reparacion_vigente_tiene_tres_celdas_fuera():
    datos = mini_reparacion()
    inst = datos["instancia"]
    vigente = datos["solucion_vigente"]
    assert _celdas_fuera_disponibilidad(inst, vigente) == 3
    assert datos["v_esperado_vigente"] == 3
