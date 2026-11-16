"""Smoke test: una semana tipo con solución conocida (datos anónimos).

Inspirada en la estructura del cronograma semanal real (lunes a sábado, mañana
de 7:00 a 13:20 con receso y taller, tarde de 14:00 a 17:00), pero sin nombres
reales. Cada docente solo tiene disponibles ciertos días, de modo que el agente
debe "descubrir" en qué día va cada módulo:

* Fotografía (D1): solo martes.      * Acondicionamiento (D2): mié y vie mañana.
* Perfilación (D3): solo jueves.     * Penal especial (D4): solo sábado mañana.
* Atención a víctimas (D5, virtual): solo lunes en la tarde.
* Práctica de tiro (sin docente): requiere el polígono.

La solución de referencia (la del cronograma real) existe, así que todo
algoritmo correcto debe llegar a v = 0. La variante "imposible" agrega un segundo
bloque de 5 h para D3, que solo tiene el jueves: no caben dos mañanas de 5 h
consecutivas en un día, así que v > 0 y el validador debe explicar por qué.

Uso: python -m herramientas.smoke_semana [--variante factible|imposible]
"""

from __future__ import annotations

import argparse

from planificador.algoritmos.base import Limites
from planificador.algoritmos.registro import NOMBRES, crear_solver
from planificador.core.modelo import (
    Bloque, Dia, Docente, Franja, Grupo, Instancia, Posicion, Salon)
from planificador.core.validador import validar

DIAS = ("LUN", "MAR", "MIE", "JUE", "VIE", "SAB")
MANANA = range(0, 6)   # F1..F6 (7:00 a 13:20)
TARDE = range(6, 8)    # F7..F8 (14:00 a 17:00)

NOMBRE_MODULO = {
    "FOTO": "Fotografía judicial", "ACOND": "Acondicionamiento físico",
    "PERF": "Perfilación criminal", "PENAL": "Derecho penal especial",
    "VICT": "Atención a víctimas", "TIRO": "Práctica de tiro",
}


def _h(hh, mm=0):
    return hh * 60 + mm


def _celdas(dias, franjas):
    return frozenset((d, h) for d in dias for h in franjas)


def instancia_semana(variante: str = "factible") -> Instancia:
    """Construye la semana tipo. ``variante``: "factible" o "imposible"."""
    franjas = (
        Franja("F1", _h(7), _h(8), extrema=True),
        Franja("F2", _h(8), _h(9)),
        Franja("F3", _h(9), _h(10)),
        Franja("F4", _h(10, 20), _h(11, 20)),   # receso 10:00-10:20 entre F3 y F4
        Franja("F5", _h(11, 20), _h(12, 20)),
        Franja("F6", _h(12, 20), _h(13, 20)),   # franja de taller
        Franja("F7", _h(14), _h(15, 30)),
        Franja("F8", _h(15, 30), _h(17), extrema=True),
    )
    dias = tuple(Dia(i, 0, i) for i in range(6))
    todos = range(6)
    salones = (
        Salon("AULA1", "AULA", 30, sede="Principal"),
        Salon("POLIGONO", "POLIGONO", 25, sede="Externa"),
        Salon("VIRTUAL", "VIRTUAL", None, virtual=True),
    )
    docentes = (
        Docente("D1", "Docente 1", _celdas([1], range(8))),
        Docente("D2", "Docente 2", _celdas([2, 4], MANANA)),
        Docente("D3", "Docente 3", _celdas([3], range(8))),
        Docente("D4", "Docente 4", _celdas([5], MANANA)),
        Docente("D5", "Docente 5", _celdas([0], TARDE)),
    )
    # Ventana del grupo: toda la semana salvo la tarde del sábado.
    ventana = _celdas(todos, range(8)) - _celdas([5], TARDE)
    grupos = (Grupo("G1", 19, ventana, max_franjas_dia=8),)
    bloques = [
        Bloque("FOTO-T", "FOTO", 5, ("G1",), "D1", "TEORIA", "AULA"),
        Bloque("FOTO-L", "FOTO", 1, ("G1",), "D1", "TALLER", "AULA"),
        Bloque("ACOND-T", "ACOND", 5, ("G1",), "D2", "TEORIA", "AULA"),
        Bloque("ACOND-P", "ACOND", 5, ("G1",), "D2", "PRACTICA", "AULA"),
        Bloque("PERF-T", "PERF", 5, ("G1",), "D3", "TEORIA", "AULA"),
        Bloque("PERF-L", "PERF", 1, ("G1",), "D3", "TALLER", "AULA"),
        Bloque("PENAL-T", "PENAL", 5, ("G1",), "D4", "TEORIA", "AULA"),
        Bloque("PENAL-L", "PENAL", 1, ("G1",), "D4", "TALLER", "AULA"),
        Bloque("VICT", "VICT", 2, ("G1",), "D5", "TEORIA", None, virtual=True),
        Bloque("TIRO", "TIRO", 2, ("G1",), None, "PRACTICA", "POLIGONO"),
    ]
    if variante == "imposible":
        bloques.append(
            Bloque("PERF-T2", "PERF", 5, ("G1",), "D3", "TEORIA", "AULA"))
    elif variante != "factible":
        raise ValueError("variante debe ser 'factible' o 'imposible'")
    return Instancia(dias, franjas, salones, docentes, grupos, tuple(bloques),
                     nombre=f"semana_tipo_{variante}")


def solucion_referencia() -> dict:
    """La semana del cronograma real (v = 0 en la variante factible)."""
    P = Posicion
    return {
        "VICT": P(0, 6, "VIRTUAL"),
        "FOTO-T": P(1, 0, "AULA1"), "FOTO-L": P(1, 5, "AULA1"),
        "ACOND-T": P(2, 0, "AULA1"),
        "PERF-T": P(3, 0, "AULA1"), "PERF-L": P(3, 5, "AULA1"),
        "ACOND-P": P(4, 0, "AULA1"), "TIRO": P(4, 6, "POLIGONO"),
        "PENAL-T": P(5, 0, "AULA1"), "PENAL-L": P(5, 5, "AULA1"),
    }


def grilla_texto(instancia: Instancia, asignacion: dict) -> str:
    """Horario del grupo como tabla de texto (franjas × días)."""
    celda = {}
    for b, pos in asignacion.items():
        for k in range(instancia.bloque[b].duracion):
            celda[(pos.dia, pos.franja + k)] = b
    ancho = 10
    lineas = ["FRANJA      " + "".join(d.ljust(ancho) for d in DIAS)]
    for h, fr in enumerate(instancia.franjas):
        hora = f"{fr.inicio // 60:02d}:{fr.inicio % 60:02d}"
        fila = "".join(celda.get((d, h), "·").ljust(ancho) for d in range(6))
        lineas.append(f"{fr.id} {hora}    {fila}")
        if fr.id == "F3":
            lineas.append("   10:00    " + "RECESO".center(ancho * 6, "-"))
    return "\n".join(lineas)


def ejecutar(variante: str = "factible", segundos: float = 20.0) -> dict:
    """Corre los 4 algoritmos y devuelve {nombre: Resultado}."""
    inst = instancia_semana(variante)
    return {n: crear_solver(n).resolver(inst, limites=Limites(max_segundos=segundos))
            for n in NOMBRES}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--variante", default="factible",
                    choices=("factible", "imposible"))
    args = ap.parse_args(argv)
    inst = instancia_semana(args.variante)
    print(f"== Smoke test: {inst.nombre} ({len(inst.bloques)} bloques) ==\n")
    if args.variante == "factible":
        ref = validar(inst, solucion_referencia())
        print(f"Solución de referencia: v = {ref.violaciones.total}, "
              f"F = {ref.F:.1f}\n")
    resultados = ejecutar(args.variante)
    print(f"{'algoritmo':14}{'v':>4}{'F':>9}{'tiempo':>10}{'nodos':>8}  fin")
    for nombre, r in resultados.items():
        rep = validar(inst, r.asignacion)
        ok = "✔" if rep.violaciones.total == r.v else "✘ (validador difiere)"
        print(f"{nombre:14}{r.v:>4}{r.F:>9.1f}{r.tiempo_s:>9.3f}s"
              f"{r.nodos_expandidos:>8}  {r.terminado_por} {ok}")
    mejor = min(resultados.values(), key=lambda r: r.F)
    print(f"\nHorario de {mejor.algoritmo} (grupo G1):\n")
    print(grilla_texto(inst, mejor.asignacion))
    rep = validar(inst, mejor.asignacion)
    if rep.problemas:
        print("\nProblemas detectados por el validador:")
        for p in rep.problemas:
            print(f"  - {p}")
    print("\nMódulos: " + ", ".join(f"{k} = {v}" for k, v in NOMBRE_MODULO.items()))


if __name__ == "__main__":
    main()
