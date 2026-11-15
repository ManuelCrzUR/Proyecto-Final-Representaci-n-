"""Violaciones duras v(X), penalizaciones blandas f(X) y costo F(X).

El cálculo principal son funciones sobre ``(instancia, asignacion)``
(``_violaciones_de``, ``_desglose_de``); las funciones públicas reciben un
``Estado`` y solo usan ``.instancia`` y ``.asignacion``.

Decisiones sobre casos no cubiertos por el contrato:

* Posición fuera de rango (día fuera de 0..D-1, o ``franja + duracion > H``
  o franja negativa), o salón inexistente: el bloque cuenta una vez en
  ``Violaciones.salon``. Sus celdas siguen contando en disponibilidad,
  ventana y conflicto (pertenencia a conjuntos), pero un bloque con posición
  fuera de rango se excluye por completo de f (no tiene franjas válidas).
* Salón inválido (cuenta 1 por bloque): salón inexistente, posición fuera de
  rango, bloque virtual en salón no virtual o presencial en virtual, y, solo
  si el salón no es virtual, tipo distinto (cuando ``tipo_salon`` no es None)
  o capacidad menor que E(m).
* ``cambio_sede``: se ignoran bloques virtuales y de salón inexistente; el
  orden es por franja de inicio y, en empate, por id de bloque.
"""

from __future__ import annotations

from collections import Counter
from typing import Mapping

from planificador.core.conflictos import construir_conflictos
from planificador.core.modelo import Instancia, Violaciones, celdas_de

CLAVES_F = ("hueco_docente", "hueco_grupo", "dispersion_docente",
            "carga_grupo", "hora_extrema", "cambio_sede")


def _gamma(instancia: Instancia) -> dict:
    """Γ de la instancia, memoizado en la propia instancia."""
    cache = instancia.__dict__
    if "_gamma_costo" not in cache:
        cache["_gamma_costo"] = construir_conflictos(instancia)
    return cache["_gamma_costo"]


def _en_rango(instancia, bloque, pos) -> bool:
    return (0 <= pos.dia < instancia.num_dias and pos.franja >= 0
            and pos.franja + bloque.duracion <= instancia.num_franjas)


def _salon_invalido(instancia, bloque, pos) -> bool:
    if not _en_rango(instancia, bloque, pos):
        return True
    salon = instancia.salon.get(pos.salon)
    if salon is None or bloque.virtual != salon.virtual:
        return True
    if salon.virtual:
        return False
    if bloque.tipo_salon is not None and bloque.tipo_salon != salon.tipo:
        return True
    return (salon.capacidad is not None
            and salon.capacidad < instancia.estudiantes(bloque.id))


# --------------------------------------------------------------------------
# Violaciones
# --------------------------------------------------------------------------

def _violaciones_de(instancia: Instancia,
                    asignacion: Mapping) -> Violaciones:
    """v(X) desglosado, calculado sobre un dict bloque_id -> Posicion."""
    colocados = {b.id: b for b in instancia.bloques if b.id in asignacion}
    celdas = {m: celdas_de(asignacion[m], b.duracion)
              for m, b in colocados.items()}
    sin_ubicar = len(instancia.bloques) - len(colocados)

    disponibilidad = ventana = salon_inv = 0
    ocupacion: Counter = Counter()
    for m, b in colocados.items():
        pos = asignacion[m]
        if b.docente_id is not None:
            disp = instancia.docente[b.docente_id].disponibilidad
            disponibilidad += sum(1 for c in celdas[m] if c not in disp)
        for g in b.grupos:
            vent = instancia.grupo[g].ventana
            ventana += sum(1 for c in celdas[m] if c not in vent)
        if _salon_invalido(instancia, b, pos):
            salon_inv += 1
        salon = instancia.salon.get(pos.salon)
        if salon is not None and not salon.virtual:
            for c in celdas[m]:
                ocupacion[(pos.salon, c)] += 1
    choques = sum(k - 1 for k in ocupacion.values() if k > 1)

    gamma = _gamma(instancia)
    conflicto = 0
    for m in colocados:
        for n in gamma[m]:
            if m < n and n in colocados:
                conflicto += len(set(celdas[m]) & set(celdas[n]))
    return Violaciones(sin_ubicar, disponibilidad, ventana, conflicto,
                       choques + salon_inv)


def violaciones(estado) -> Violaciones:
    """Desglose de v(X) para un estado."""
    return _violaciones_de(estado.instancia, dict(estado.asignacion))


def v(estado) -> int:
    """v(X): total de violaciones duras."""
    return violaciones(estado).total


# --------------------------------------------------------------------------
# Penalizaciones blandas
# --------------------------------------------------------------------------

def _huecos(ocupacion: dict) -> int:
    """Huecos de una entidad; ``ocupacion``: día -> conjunto de franjas."""
    total = 0
    for franjas in ocupacion.values():
        if franjas:
            total += max(franjas) - min(franjas) + 1 - len(franjas)
    return total


def _desglose_de(instancia: Instancia, asignacion: Mapping) -> dict:
    """φ_i sin pesos; solo se consideran bloques con posición en rango."""
    H = instancia.num_franjas
    docs: dict = {}
    grps: dict = {}
    extrema = cambio = 0
    por_grupo_dia: dict = {}
    for b in instancia.bloques:
        pos = asignacion.get(b.id)
        if pos is None or not _en_rango(instancia, b, pos):
            continue
        franjas = range(pos.franja, pos.franja + b.duracion)
        extrema += sum(1 for h in franjas if instancia.franjas[h].extrema)
        duenos = [docs.setdefault(b.docente_id, {})] if b.docente_id else []
        duenos += [grps.setdefault(g, {}) for g in b.grupos]
        for ocup in duenos:
            ocup.setdefault(pos.dia, set()).update(franjas)
        salon = instancia.salon.get(pos.salon)
        if not b.virtual and salon is not None:
            for g in b.grupos:
                por_grupo_dia.setdefault((g, pos.dia), []).append(
                    (pos.franja, b.id, salon.sede))
    for lista in por_grupo_dia.values():
        lista.sort()
        cambio += sum(1 for a, c in zip(lista, lista[1:]) if a[2] != c[2])

    dispersion = 0
    for ocup in docs.values():
        total = sum(len(s) for s in ocup.values())
        dispersion += max(0, len(ocup) - -(-total // H))
    carga = 0
    for entidades, indice in ((grps, instancia.grupo),
                              (docs, instancia.docente)):
        for ent_id, ocup in entidades.items():
            tope = indice[ent_id].max_franjas_dia
            if tope is not None:
                carga += sum(max(0, len(s) - tope) for s in ocup.values())
    return {
        "hueco_docente": float(sum(_huecos(o) for o in docs.values())),
        "hueco_grupo": float(sum(_huecos(o) for o in grps.values())),
        "dispersion_docente": float(dispersion),
        "carga_grupo": float(carga),
        "hora_extrema": float(extrema),
        "cambio_sede": float(cambio),
    }


def _f_de(instancia: Instancia, asignacion: Mapping) -> float:
    w = instancia.pesos
    phi = _desglose_de(instancia, asignacion)
    return sum(getattr(w, clave) * phi[clave] for clave in CLAVES_F)


def desglose_f(estado) -> dict[str, float]:
    """φ_i sin pesos, con las claves de ``CLAVES_F``."""
    return _desglose_de(estado.instancia, dict(estado.asignacion))


def f(estado) -> float:
    """f(X) = Σ w_i φ_i."""
    return _f_de(estado.instancia, dict(estado.asignacion))


def cota_superior_f(instancia: Instancia) -> float:
    """Cota superior de f sobre cualquier asignación (pesos >= 0).

    Con D días, H franjas, |T| docentes, |G| grupos, δ(m) duración y
    γ(m) = número de grupos del bloque::

        w_hd*|T|*D*H + w_hg*|G|*D*H + w_dis*|T|*D
        + w_car*(|G|+|T|)*D*H + w_ext*Σδ(m) + w_sed*Σγ(m)

    Demostración, término a término: huecos por entidad y día son
    (último - primero + 1) - #ocupadas <= H, y hay |T|·D (|G|·D) pares
    entidad-día. Dispersión: días con clase <= D por docente. Carga: el
    exceso por entidad y día es <= H y hay (|G|+|T|)·D pares. Hora extrema:
    cada bloque aporta a lo sumo δ(m) franjas. Cambio de sede: por grupo y
    día los pares consecutivos son (n - 1) para n bloques, luego en total
    <= Σ_g n_g = Σ_m γ(m).
    """
    w = instancia.pesos
    D, H = instancia.num_dias, instancia.num_franjas
    nt, ng = len(instancia.docentes), len(instancia.grupos)
    dur = sum(b.duracion for b in instancia.bloques)
    gam = sum(len(b.grupos) for b in instancia.bloques)
    return float(w.hueco_docente * nt * D * H
                 + w.hueco_grupo * ng * D * H
                 + w.dispersion_docente * nt * D
                 + w.carga_grupo * (ng + nt) * D * H
                 + w.hora_extrema * dur
                 + w.cambio_sede * gam)


def lam(instancia: Instancia) -> float:
    """λ: ``pesos.lam`` si está definido, si no ``cota_superior_f + 1``."""
    if instancia.pesos.lam is not None:
        return float(instancia.pesos.lam)
    return cota_superior_f(instancia) + 1.0


def F(estado) -> float:
    """F(X) = f(X) + λ·v(X)."""
    return f(estado) + lam(estado.instancia) * v(estado)


def recompensa(antes, despues) -> float:
    """F(antes) - F(despues)."""
    return F(antes) - F(despues)
