"""Acciones sobre el estado: legalidad, aplicación y generación.

Implementa la API de ``docs/contrato.md`` (Sprint 2, ``core/acciones.py``).

La legalidad cubre forma, salón y el tope diario por serie (C14: la suma de
duraciones de los bloques de una serie en un día no excede
``Bloque.max_franjas_dia``); NO filtra disponibilidad (A), ventana (W) ni
conflictos (Γ), que se cuentan en v(X).

Decisiones ante ambigüedades:

* Ids de bloque o salón desconocidos hacen que ``es_legal`` devuelva False.
* ``Reubicar`` a la posición actual y ``CambiarSalon`` al salón actual son
  legales según las reglas (no-ops); solo ``acciones_legales`` los omite.
* ``aplicar_en_sitio`` valida la legalidad (``ValueError``, sin mutar). Por
  tanto, deshacer con la inversa puede fallar si el estado inicial traía una
  posición ilegal por salón (tipo/capacidad) que la acción quitó o movió.
* ``acciones_legales`` es un generador perezoso sobre el estado vivo: no debe
  mutarse el estado mientras se itera (use ``list(...)`` si hace falta).
"""

from __future__ import annotations

from typing import Iterator

from planificador.core.estado import Estado
from planificador.core.modelo import (Accion, Anadir, CambiarSalon, Eliminar,
                                      Intercambiar, Posicion, Reubicar,
                                      celdas_de)


# --------------------------------------------------------------------------
# Legalidad de una posición
# --------------------------------------------------------------------------

def _salon_compatible(estado: Estado, bloque_id: str, salon_id: str) -> bool:
    """Reglas de salón: modalidad, tipo y capacidad (sin ocupación)."""
    inst = estado.instancia
    salon = inst.salon.get(salon_id)
    if salon is None:
        return False
    bloque = inst.bloque[bloque_id]
    if bloque.virtual != salon.virtual:
        return False
    if salon.virtual:
        return True
    if bloque.tipo_salon is not None and bloque.tipo_salon != salon.tipo:
        return False
    if (salon.capacidad is not None
            and salon.capacidad < inst.estudiantes(bloque_id)):
        return False
    return True


def _cabe(estado: Estado, bloque_id: str, pos: Posicion) -> bool:
    """Forma: día válido y franja + duración <= H."""
    inst = estado.instancia
    dur = inst.bloque[bloque_id].duracion
    return (0 <= pos.dia < inst.num_dias and 0 <= pos.franja
            and pos.franja + dur <= inst.num_franjas)


def _libre(estado: Estado, bloque_id: str, pos: Posicion,
           ignorar: tuple = ()) -> bool:
    """Celdas libres en el salón (siempre True si es virtual); ignora los
    bloques de ``ignorar``."""
    inst = estado.instancia
    if inst.salon[pos.salon].virtual:
        return True
    dur = inst.bloque[bloque_id].duracion
    for c in celdas_de(pos, dur):
        otro = estado.ocupante(pos.salon, c)
        if otro is not None and otro not in ignorar:
            return False
    return True


def _usado_serie(estado: Estado, bloque_id: str, dia: int,
                 ignorar: tuple = ()) -> int:
    """Franjas de la serie del bloque ese día, sin contar a ``ignorar`` ni al
    propio bloque (que se quitaría antes de ubicarlo)."""
    inst = estado.instancia
    b = inst.bloque[bloque_id]
    usado = estado.franjas_serie(b.serie, dia)
    for o in set(ignorar) | {bloque_id}:
        po = estado.posicion(o)
        if po is not None and po.dia == dia:
            ob = inst.bloque[o]
            if ob.serie == b.serie:
                usado -= ob.duracion
    return usado


def _tope_serie(estado: Estado, bloque_id: str, pos: Posicion,
                ignorar: tuple = ()) -> bool:
    """C14: ubicar el bloque en ``pos`` no excede el tope diario de su serie."""
    b = estado.instancia.bloque[bloque_id]
    if b.serie is None or b.max_franjas_dia is None:
        return True
    return (_usado_serie(estado, bloque_id, pos.dia, ignorar) + b.duracion
            <= b.max_franjas_dia)


def dias_sin_cupo(estado: Estado, bloque_id: str):
    """Días en que el tope de la serie impide ubicar el bloque (C14).

    ``None`` si el bloque no tiene tope (caso sin topes: sin costo extra).
    """
    b = estado.instancia.bloque[bloque_id]
    if b.serie is None or b.max_franjas_dia is None:
        return None
    return frozenset(
        d for d in range(estado.instancia.num_dias)
        if _usado_serie(estado, bloque_id, d) + b.duracion
        > b.max_franjas_dia)


def _pos_legal(estado: Estado, bloque_id: str, pos: Posicion,
               ignorar: tuple = ()) -> bool:
    return (_cabe(estado, bloque_id, pos)
            and _salon_compatible(estado, bloque_id, pos.salon)
            and _libre(estado, bloque_id, pos, ignorar)
            and _tope_serie(estado, bloque_id, pos, ignorar))


# --------------------------------------------------------------------------
# es_legal
# --------------------------------------------------------------------------

def es_legal(estado: Estado, accion: Accion) -> bool:
    """Indica si la acción es legal en el estado."""
    inst = estado.instancia
    if isinstance(accion, Intercambiar):
        a, b = accion.bloque_a, accion.bloque_b
        if a == b or a not in inst.bloque or b not in inst.bloque:
            return False
        pa, pb = estado.posicion(a), estado.posicion(b)
        if pa is None or pb is None:
            return False
        if inst.bloque[a].duracion != inst.bloque[b].duracion:
            return False
        ign = (a, b)
        return (_pos_legal(estado, a, pb, ign)
                and _pos_legal(estado, b, pa, ign))
    bid = accion.bloque
    if bid not in inst.bloque:
        return False
    previa = estado.posicion(bid)
    if isinstance(accion, Anadir):
        return previa is None and _pos_legal(estado, bid, accion.posicion)
    if previa is None:
        return False
    if isinstance(accion, Eliminar):
        return True
    if isinstance(accion, Reubicar):
        return _pos_legal(estado, bid, accion.posicion, (bid,))
    if isinstance(accion, CambiarSalon):
        nueva = Posicion(previa.dia, previa.franja, accion.salon)
        return _pos_legal(estado, bid, nueva, (bid,))
    return False


# --------------------------------------------------------------------------
# aplicar
# --------------------------------------------------------------------------

def aplicar_en_sitio(estado: Estado, accion: Accion) -> Accion:
    """Muta el estado y devuelve la acción inversa.

    Lanza ``ValueError`` (sin mutar) si la acción es ilegal.
    """
    if not es_legal(estado, accion):
        raise ValueError(f"Acción ilegal: {accion}")
    if isinstance(accion, Anadir):
        estado._colocar(accion.bloque, accion.posicion)
        return Eliminar(accion.bloque)
    if isinstance(accion, Eliminar):
        previa = estado._quitar(accion.bloque)
        return Anadir(accion.bloque, previa)
    if isinstance(accion, Intercambiar):
        a, b = accion.bloque_a, accion.bloque_b
        pa, pb = estado._quitar(a), estado._quitar(b)
        estado._colocar(a, pb)
        estado._colocar(b, pa)
        return accion
    if isinstance(accion, Reubicar):
        previa = estado._quitar(accion.bloque)
        estado._colocar(accion.bloque, accion.posicion)
        return Reubicar(accion.bloque, previa)
    # CambiarSalon
    previa = estado._quitar(accion.bloque)
    estado._colocar(accion.bloque,
                    Posicion(previa.dia, previa.franja, accion.salon))
    return CambiarSalon(accion.bloque, previa.salon)


def aplicar(estado: Estado, accion: Accion) -> Estado:
    """Versión pura: devuelve un estado nuevo; ``ValueError`` si ilegal."""
    nuevo = estado.copiar()
    aplicar_en_sitio(nuevo, accion)
    return nuevo


# --------------------------------------------------------------------------
# Generación
# --------------------------------------------------------------------------

def posiciones_legales(estado: Estado, bloque_id: str) -> list:
    """Posiciones donde añadir el bloque, en orden (dia, franja, salon).

    Si el bloque ya está ubicado, se ignora a sí mismo en la ocupación.
    """
    inst = estado.instancia
    dur = inst.bloque[bloque_id].duracion
    salones = [s for s in estado._salones_ord
               if _salon_compatible(estado, bloque_id, s)]
    virtual = {s: inst.salon[s].virtual for s in salones}
    sin_cupo = dias_sin_cupo(estado, bloque_id) or ()
    resultado = []
    for dia in range(inst.num_dias):
        if dia in sin_cupo:
            continue
        for franja in range(inst.num_franjas - dur + 1):
            celdas = [(dia, franja + i) for i in range(dur)]
            for s in salones:
                if not virtual[s]:
                    libre = True
                    for c in celdas:
                        otro = estado.ocupante(s, c)
                        if otro is not None and otro != bloque_id:
                            libre = False
                            break
                    if not libre:
                        continue
                resultado.append(Posicion(dia, franja, s))
    return resultado


def acciones_legales(estado: Estado) -> Iterator[Accion]:
    """Genera todas las acciones legales en orden determinista.

    Orden: Anadir (U por id) ; Eliminar (ubicados por id) ; Reubicar ;
    CambiarSalon ; Intercambiar (pares a < b por id).
    """
    sin = sorted(estado.sin_ubicar())
    for b in sin:
        for pos in posiciones_legales(estado, b):
            yield Anadir(b, pos)
    ubicados = sorted(estado.asignacion)
    for b in ubicados:
        yield Eliminar(b)
    legales = {b: posiciones_legales(estado, b) for b in ubicados}
    for b in ubicados:
        actual = estado.posicion(b)
        for pos in legales[b]:
            if pos != actual:
                yield Reubicar(b, pos)
    for b in ubicados:
        actual = estado.posicion(b)
        for pos in legales[b]:
            if (pos.dia == actual.dia and pos.franja == actual.franja
                    and pos.salon != actual.salon):
                yield CambiarSalon(b, pos.salon)
    inst = estado.instancia
    for i, a in enumerate(ubicados):
        da = inst.bloque[a].duracion
        for b in ubicados[i + 1:]:
            if inst.bloque[b].duracion != da:
                continue
            accion = Intercambiar(a, b)
            if es_legal(estado, accion):
                yield accion
