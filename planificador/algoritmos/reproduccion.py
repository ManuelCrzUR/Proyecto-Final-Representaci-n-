"""Reproducción de una ``Traza`` paso a paso (dueño: orquestador).

Convierte la traza de cualquier solver en la secuencia de asignaciones que
muestra la animación:

* ``add``  → ubica ``evento.bloque`` en ``evento.posicion``.
* ``del``  → quita ``evento.bloque``.
* Cualquier evento con ``asignacion`` (``expandir`` en A*, avara, beam) → el
  estado pasa a ser la foto.
* ``solucion`` / ``fin`` → si se pasa ``asignacion_final`` (la del Resultado),
  el estado pasa a ser esa: en A*/avara/beam la hoja meta no se expande y por
  eso su foto no está en la traza.
* Otros eventos no cambian la asignación (se muestran como anotaciones).

Así la interfaz distingue el proceso de búsqueda (todos los cuadros) de la
solución final (``Resultado.asignacion``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Cuadro:
    """Un paso de la animación."""

    indice: int
    evento: object          # base.Evento
    asignacion: dict        # bloque_id -> Posicion tras aplicar el evento
    resaltado: str | None   # bloque afectado por el evento (si hay)


def cuadros(traza, asignacion_inicial: dict | None = None,
            asignacion_final: dict | None = None):
    """Genera los ``Cuadro`` de la traza partiendo de ``asignacion_inicial``."""
    actual = dict(asignacion_inicial or {})
    for i, ev in enumerate(traza.eventos):
        if ev.asignacion is not None:
            actual = dict(ev.asignacion)
        elif ev.tipo in ("solucion", "fin") and asignacion_final is not None:
            actual = dict(asignacion_final)
        elif ev.tipo == "add" and ev.bloque is not None and ev.posicion is not None:
            actual[ev.bloque] = ev.posicion
        elif ev.tipo == "del" and ev.bloque is not None:
            actual.pop(ev.bloque, None)
        yield Cuadro(i, ev, dict(actual), ev.bloque)


def lista_cuadros(traza, asignacion_inicial=None, max_cuadros=None,
                  asignacion_final=None) -> list:
    """Versión en lista; si ``max_cuadros`` se da, muestrea uniformemente
    conservando siempre el primer y el último cuadro."""
    todos = list(cuadros(traza, asignacion_inicial, asignacion_final))
    if max_cuadros is None or len(todos) <= max_cuadros or max_cuadros < 2:
        return todos
    paso = (len(todos) - 1) / (max_cuadros - 1)
    indices = sorted({round(k * paso) for k in range(max_cuadros)})
    return [todos[i] for i in indices]


def cuadros_de_resultado(resultado, asignacion_inicial=None, max_cuadros=None):
    """Atajo recomendado: reproduce ``resultado.traza`` terminando en
    ``resultado.asignacion``."""
    return lista_cuadros(resultado.traza, asignacion_inicial, max_cuadros,
                         asignacion_final=resultado.asignacion)
