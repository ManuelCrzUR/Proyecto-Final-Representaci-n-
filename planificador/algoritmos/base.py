"""Interfaz común de los algoritmos: Solver, Limites, Evento, Traza y Resultado.

CONTRATO CONGELADO (solo lo modifica el orquestador; ver ``docs/contrato.md``).

La ``Traza`` es el formato único que consume la animación de la interfaz. Para
reconstruir el horario en cualquier paso:

* Algoritmos incrementales (backtracking): basta aplicar en orden los eventos
  ``add`` (bloque, posicion) y ``del`` (bloque).
* Algoritmos que saltan entre nodos (A*, avara, beam): cada evento ``expandir``
  trae ``asignacion`` = foto completa del estado parcial expandido.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from planificador.core.modelo import Instancia, Posicion, Violaciones

TIPOS_EVENTO = (
    "expandir",     # se expande un nodo (A*/avara/beam) o un nivel (backtracking)
    "add",          # se ubica un bloque
    "del",          # se quita un bloque (deshacer)
    "podar",        # forward checking deja un dominio vacío o se descarta un nodo
    "retroceder",   # backtracking regresa un nivel
    "frontera",     # resumen de la frontera / haz (tam_frontera)
    "mejora",       # se encontró un estado mejor que el mejor conocido
    "solucion",     # se alcanzó la meta (v = 0)
    "fin",          # terminó la búsqueda (nota = motivo)
)


@dataclass(frozen=True)
class Limites:
    """Presupuesto de la búsqueda. ``None`` = sin límite."""

    max_nodos: Optional[int] = 200_000
    max_segundos: Optional[float] = 30.0
    max_eventos_traza: int = 20_000  # al superarlo se deja de registrar


@dataclass(frozen=True)
class Evento:
    paso: int
    tipo: str
    bloque: Optional[str] = None
    posicion: Optional[Posicion] = None
    F: Optional[float] = None
    v: Optional[int] = None
    f: Optional[float] = None
    tam_frontera: Optional[int] = None
    profundidad: Optional[int] = None
    asignacion: Optional[tuple] = None  # ((bloque_id, Posicion), ...) ordenada
    nota: str = ""


class Traza:
    """Lista de eventos con tope; cuenta los eventos descartados."""

    def __init__(self, max_eventos: int = 20_000):
        self.eventos: list = []
        self.max_eventos = max_eventos
        self.descartados = 0
        self._paso = 0

    def registrar(self, tipo: str, **datos) -> None:
        if tipo not in TIPOS_EVENTO:
            raise ValueError(f"Tipo de evento desconocido: {tipo}")
        self._paso += 1
        if len(self.eventos) >= self.max_eventos and tipo not in (
                "solucion", "fin"):
            self.descartados += 1
            return
        self.eventos.append(Evento(paso=self._paso, tipo=tipo, **datos))

    @property
    def truncada(self) -> bool:
        return self.descartados > 0

    def __len__(self) -> int:
        return len(self.eventos)


def foto(asignacion) -> tuple:
    """Foto inmutable y ordenada de una asignación (para ``Evento.asignacion``)."""
    return tuple(sorted(asignacion.items()))


@dataclass
class Resultado:
    algoritmo: str
    asignacion: dict            # bloque_id -> Posicion (mejor estado encontrado)
    violaciones: Violaciones
    f: float
    F: float
    tiempo_s: float
    nodos_expandidos: int
    nodos_generados: int
    terminado_por: str          # "meta" | "agotado" | "limite_nodos" | "limite_tiempo"
    traza: Traza
    parametros: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)

    @property
    def v(self) -> int:
        return self.violaciones.total

    @property
    def exito(self) -> bool:
        return self.violaciones.total == 0


class Presupuesto:
    """Controla nodos y tiempo. ``agotado()`` devuelve el motivo o None."""

    def __init__(self, limites: Limites):
        self.limites = limites
        self.inicio = time.perf_counter()
        self.nodos_expandidos = 0
        self.nodos_generados = 0

    def transcurrido(self) -> float:
        return time.perf_counter() - self.inicio

    def agotado(self) -> Optional[str]:
        lim = self.limites
        if lim.max_nodos is not None and self.nodos_expandidos >= lim.max_nodos:
            return "limite_nodos"
        if (lim.max_segundos is not None
                and self.transcurrido() >= lim.max_segundos):
            return "limite_tiempo"
        return None


class Solver(ABC):
    """Algoritmo de búsqueda. Los parámetros van en el constructor."""

    nombre: str = "solver"

    def __init__(self, **parametros):
        self.parametros = parametros

    @abstractmethod
    def resolver(self, instancia: Instancia, estado_inicial=None,
                 limites: Limites = Limites()) -> Resultado:
        """Busca un horario.

        ``estado_inicial``: ``Estado`` de partida (vacío si es None). Los bloques
        ya ubicados en él se consideran fijos salvo que el algoritmo documente lo
        contrario. No se muta: el solver trabaja sobre una copia.
        Debe respetar ``limites`` y devolver SIEMPRE un Resultado con el mejor
        estado encontrado (aunque no sea meta), evaluado con ``core.costo``.
        """
