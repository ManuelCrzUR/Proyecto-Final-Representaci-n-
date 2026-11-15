"""Instancias mini con respuesta conocida (solución y costo verificados a mano).

Cada fábrica devuelve un dict con las claves:
``instancia``, ``descripcion``, ``factible``, ``solucion`` (dict bloque ->
Posicion o None), ``v_esperado_solucion`` y, según el caso, extras como
``v_minimo`` (mínimo global, permitiendo dejar bloques sin ubicar),
``v_min_solo_anadir`` (mínimo entre estados maximales alcanzables solo con
'añadir' legal), ``solucion_vigente``, ``v_esperado_vigente`` o
``posicion_ilegal``.
"""

from planificador.core.modelo import (
    Bloque,
    Dia,
    Docente,
    Franja,
    Grupo,
    Instancia,
    Posicion,
    Salon,
)


def _franjas3():
    """Tres franjas por día; la tercera es extrema."""
    return (
        Franja("F1", 420, 480),
        Franja("F2", 480, 540),
        Franja("F3", 540, 600, extrema=True),
    )


def _dias(num_dias):
    """Días 0..num_dias-1 de una misma semana (lunes en adelante)."""
    return tuple(Dia(indice=i, semana=0, dia_semana=i) for i in range(num_dias))


def _todas(num_dias):
    """Todas las celdas (día, franja) de un horizonte de tres franjas."""
    return frozenset((d, h) for d in range(num_dias) for h in range(3))


def _mini_dos_dias(nombre, disponibilidad_t1):
    """Base de dos días compartida por ``mini_factible`` y ``mini_reparacion``."""
    todas = _todas(2)
    solo_dia_1 = frozenset((1, h) for h in range(3))
    inst = Instancia(
        nombre=nombre,
        dias=_dias(2),
        franjas=_franjas3(),
        salones=(
            Salon("S1", tipo="AULA", capacidad=30),
            Salon("S2", tipo="LAB", capacidad=10),
        ),
        docentes=(
            Docente("T1", "Docente Uno", disponibilidad_t1),
            Docente("T2", "Docente Dos", solo_dia_1),
        ),
        grupos=(
            Grupo("G1", 20, todas),
            Grupo("G2", 8, todas),
        ),
        bloques=(
            Bloque("B1", "M1", 2, ("G1",), "T1"),
            Bloque("B2", "M2", 1, ("G1",), "T2"),
            Bloque("B3", "M3", 1, ("G2",), "T1", tipo_salon="LAB"),
        ),
    )
    return inst


def mini_factible():
    """Dos días, tres bloques; existe solución factible con v = 0."""
    return {
        "instancia": _mini_dos_dias("mini_factible", _todas(2)),
        "descripcion": "Dos días, tres bloques, solución factible con v = 0.",
        "factible": True,
        "solucion": {
            "B1": Posicion(0, 0, "S1"),
            "B2": Posicion(1, 0, "S1"),
            "B3": Posicion(0, 2, "S2"),
        },
        "v_esperado_solucion": 0,
    }


def mini_infactible():
    """Un día y una sola franja: solo cabe uno de dos bloques en conflicto."""
    celda = frozenset({(0, 0)})
    inst = Instancia(
        nombre="mini_infactible",
        dias=_dias(1),
        franjas=(Franja("F1", 420, 480),),
        salones=(Salon("S1", tipo="AULA", capacidad=30),),
        docentes=(Docente("T1", "Docente Uno", celda),),
        grupos=(Grupo("G1", 10, celda),),
        bloques=(
            Bloque("B1", "M1", 1, ("G1",), "T1"),
            Bloque("B2", "M2", 1, ("G1",), "T1"),
        ),
    )
    return {
        "instancia": inst,
        "descripcion": "Un día, una franja; dos bloques no caben a la vez.",
        "factible": False,
        "solucion": None,
        "v_esperado_solucion": None,
        "v_minimo": 1,
        "v_min_solo_anadir": 1,
    }


def mini_virtual():
    """Dos bloques virtuales simultáneos en el salón virtual, con v = 0."""
    dias = 1
    inst = Instancia(
        nombre="mini_virtual",
        dias=_dias(dias),
        franjas=_franjas3(),
        salones=(
            Salon("SV", tipo="VIRTUAL", capacidad=None, virtual=True),
            Salon("S1", tipo="AULA", capacidad=5),
        ),
        docentes=(
            Docente("T1", "Docente Uno", _todas(dias)),
            Docente("T2", "Docente Dos", _todas(dias)),
        ),
        grupos=(
            Grupo("G1", 100, _todas(dias)),
            Grupo("G2", 50, _todas(dias)),
        ),
        bloques=(
            Bloque("B1", "M1", 1, ("G1",), "T1", virtual=True),
            Bloque("B2", "M2", 1, ("G2",), "T2", virtual=True),
        ),
    )
    return {
        "instancia": inst,
        "descripcion": "Dos bloques virtuales en el mismo instante; v = 0.",
        "factible": True,
        "solucion": {
            "B1": Posicion(0, 0, "SV"),
            "B2": Posicion(0, 0, "SV"),
        },
        "v_esperado_solucion": 0,
        "posicion_ilegal": ("B1", Posicion(0, 0, "S1")),
    }


def mini_sin_disponibilidad():
    """El docente no tiene disponibilidad: sus dos franjas violan A."""
    inst = Instancia(
        nombre="mini_sin_disponibilidad",
        dias=_dias(1),
        franjas=_franjas3(),
        salones=(Salon("S1", tipo="AULA", capacidad=30),),
        docentes=(Docente("T1", "Docente Uno", frozenset()),),
        grupos=(Grupo("G1", 10, _todas(1)),),
        bloques=(Bloque("B1", "M1", 2, ("G1",), "T1"),),
    )
    return {
        "instancia": inst,
        "descripcion": "Docente sin disponibilidad; dos franjas violadas.",
        "factible": False,
        "solucion": {"B1": Posicion(0, 0, "S1")},
        "v_esperado_solucion": 2,
        "v_minimo": 1,  # saltar el bloque (|U| = 1) es mejor que ubicarlo
        "v_min_solo_anadir": 2,  # ubicándolo a la fuerza: 2 franjas sin A
    }


def mini_reparacion():
    """Solución vigente deja de servir al cambiar la disponibilidad de T1."""
    solucion_vigente = mini_factible()["solucion"]
    return {
        "instancia": _mini_dos_dias(
            "mini_reparacion", frozenset((1, h) for h in range(3))
        ),
        "descripcion": (
            "Igual que mini_factible, pero T1 solo está disponible el día 1."
        ),
        "factible": True,
        "solucion": {
            "B1": Posicion(1, 1, "S1"),
            "B2": Posicion(1, 0, "S1"),
            "B3": Posicion(1, 0, "S2"),
        },
        "v_esperado_solucion": 0,
        "solucion_vigente": solucion_vigente,
        "v_esperado_vigente": 3,
    }


TODAS_LAS_FIXTURES = [
    mini_factible,
    mini_infactible,
    mini_virtual,
    mini_sin_disponibilidad,
    mini_reparacion,
]
