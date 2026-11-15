"""Estado de la búsqueda: asignación parcial X con índices de ocupación.

Implementa la API de ``docs/contrato.md`` (Sprint 2, ``core/estado.py``).

Índices mantenidos (todas las consultas son O(1) o O(duración)):

* ``(salon_id, celda) -> bloque`` solo para salones NO virtuales.
* ``celda -> conjunto de bloques`` en cualquier salón (incluye virtuales).
* ``U(X)``: conjunto de bloques sin ubicar.
* API extra pública y estable: ``ocupacion_docente(docente_id, celda)`` y
  ``ocupacion_grupo(grupo_id, celda)``, que devuelven cuántos bloques ubicados
  del docente / grupo ocupan esa celda (0 o 1 si no hay conflictos).

Decisión sobre estados iniciales: el constructor valida que cada posición
quepa (día válido, ``franja + duracion <= H``, salón existente) pero NO exige
legalidad de salón (tipo, capacidad, modalidad): un estado "vigente" puede
venir dado. Si dos bloques chocan en un salón no virtual, el índice
salón×celda no puede representar ambos y se lanza ``ValueError``.

Un ``Estado`` es mutable; ``__hash__`` se calcula sobre ``clave()`` en el
momento de la llamada, por lo que no debe mutarse mientras sea clave de un
dict o miembro de un set.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Hashable, Optional

from planificador.core.modelo import Celda, Instancia, Posicion, celdas_de


class Estado:
    """Asignación parcial bloque_id -> Posicion con índices de ocupación."""

    __slots__ = ("instancia", "_asig", "_vista", "_sin", "_salon_celda",
                 "_celda", "_docente", "_grupo", "_salones_ord")

    def __init__(self, instancia: Instancia,
                 asignacion: Optional[dict] = None) -> None:
        self.instancia = instancia
        self._asig: dict = {}
        self._vista = MappingProxyType(self._asig)
        self._sin: set = {b.id for b in instancia.bloques}
        self._salon_celda: dict = {}
        self._celda: dict = {}
        self._docente: dict = {}
        self._grupo: dict = {}
        # Salones ordenados por id, compartido entre copias (inmutable).
        self._salones_ord = tuple(sorted(s.id for s in instancia.salones))
        for bloque_id, pos in (asignacion or {}).items():
            self._validar_forma(bloque_id, pos)
            self._colocar(bloque_id, pos)

    def _validar_forma(self, bloque_id: str, pos: Posicion) -> None:
        inst = self.instancia
        bloque = inst.bloque.get(bloque_id)
        if bloque is None:
            raise ValueError(f"Bloque desconocido: {bloque_id}")
        if not 0 <= pos.dia < inst.num_dias:
            raise ValueError(f"Bloque {bloque_id}: día {pos.dia} inválido")
        if pos.franja < 0 or pos.franja + bloque.duracion > inst.num_franjas:
            raise ValueError(
                f"Bloque {bloque_id}: franja {pos.franja} no cabe con "
                f"duración {bloque.duracion}")
        if pos.salon not in inst.salon:
            raise ValueError(f"Bloque {bloque_id}: salón {pos.salon} "
                             "desconocido")

    # --- consultas -----------------------------------------------------
    @property
    def asignacion(self):
        """Vista de solo lectura (en vivo) bloque_id -> Posicion."""
        return self._vista

    def sin_ubicar(self) -> frozenset:
        """U(X): bloques sin ubicar."""
        return frozenset(self._sin)

    def posicion(self, bloque_id: str) -> Optional[Posicion]:
        return self._asig.get(bloque_id)

    def bloques_en(self, celda: Celda) -> frozenset:
        """Bloques que ocupan la celda en cualquier salón."""
        return frozenset(self._celda.get(celda, ()))

    def ocupante(self, salon_id: str, celda: Celda) -> Optional[str]:
        """Bloque en ese salón y celda (None si libre o salón virtual)."""
        return self._salon_celda.get((salon_id, celda))

    def ocupacion_docente(self, docente_id: str, celda: Celda) -> int:
        """Número de bloques ubicados del docente que ocupan la celda."""
        return self._docente.get((docente_id, celda), 0)

    def ocupacion_grupo(self, grupo_id: str, celda: Celda) -> int:
        """Número de bloques ubicados del grupo que ocupan la celda."""
        return self._grupo.get((grupo_id, celda), 0)

    # --- copia, identidad ----------------------------------------------
    def copiar(self) -> "Estado":
        """Copia barata: copia superficial de índices; la instancia se
        comparte."""
        nuevo = Estado.__new__(Estado)
        nuevo.instancia = self.instancia
        nuevo._asig = dict(self._asig)
        nuevo._vista = MappingProxyType(nuevo._asig)
        nuevo._sin = set(self._sin)
        nuevo._salon_celda = dict(self._salon_celda)
        nuevo._celda = {c: set(s) for c, s in self._celda.items()}
        nuevo._docente = dict(self._docente)
        nuevo._grupo = dict(self._grupo)
        nuevo._salones_ord = self._salones_ord
        return nuevo

    def clave(self) -> Hashable:
        """frozenset de (bloque_id, Posicion); igual para asignaciones
        iguales."""
        return frozenset(self._asig.items())

    def __eq__(self, otro: object) -> bool:
        if not isinstance(otro, Estado):
            return NotImplemented
        return self._asig == otro._asig

    def __hash__(self) -> int:
        return hash(self.clave())

    def __repr__(self) -> str:
        return (f"Estado({self.instancia.nombre!r}, "
                f"ubicados={len(self._asig)}, sin_ubicar={len(self._sin)})")

    # --- mutadores de bajo nivel (solo acciones.py) ---------------------
    def _colocar(self, bloque_id: str, pos: Posicion) -> None:
        """Ubica un bloque (no ubicado) y actualiza índices.

        Lanza ``ValueError`` (sin mutar) si ya está ubicado o si choca con
        otro bloque en un salón no virtual.
        """
        if bloque_id in self._asig:
            raise ValueError(f"Bloque {bloque_id} ya está ubicado")
        inst = self.instancia
        bloque = inst.bloque[bloque_id]
        celdas = celdas_de(pos, bloque.duracion)
        virtual = inst.salon[pos.salon].virtual
        if not virtual:
            for c in celdas:
                otro = self._salon_celda.get((pos.salon, c))
                if otro is not None:
                    raise ValueError(
                        f"Bloque {bloque_id} choca con {otro} en el salón "
                        f"{pos.salon}, celda {c}")
        self._asig[bloque_id] = pos
        self._sin.discard(bloque_id)
        for c in celdas:
            if not virtual:
                self._salon_celda[(pos.salon, c)] = bloque_id
            self._celda.setdefault(c, set()).add(bloque_id)
            if bloque.docente_id is not None:
                k = (bloque.docente_id, c)
                self._docente[k] = self._docente.get(k, 0) + 1
            for g in bloque.grupos:
                k = (g, c)
                self._grupo[k] = self._grupo.get(k, 0) + 1

    def _quitar(self, bloque_id: str) -> Posicion:
        """Quita un bloque ubicado, actualiza índices y devuelve su
        posición previa."""
        pos = self._asig.pop(bloque_id)
        inst = self.instancia
        bloque = inst.bloque[bloque_id]
        virtual = inst.salon[pos.salon].virtual
        self._sin.add(bloque_id)
        for c in celdas_de(pos, bloque.duracion):
            if not virtual:
                del self._salon_celda[(pos.salon, c)]
            ocupantes = self._celda[c]
            ocupantes.discard(bloque_id)
            if not ocupantes:
                del self._celda[c]
            if bloque.docente_id is not None:
                self._decrementar(self._docente, (bloque.docente_id, c))
            for g in bloque.grupos:
                self._decrementar(self._grupo, (g, c))
        return pos

    @staticmethod
    def _decrementar(indice: dict, clave: tuple) -> None:
        if indice[clave] <= 1:
            del indice[clave]
        else:
            indice[clave] -= 1
