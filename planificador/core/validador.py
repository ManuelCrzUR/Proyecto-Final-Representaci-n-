"""Validador independiente (oráculo): recalcula v, f y F desde cero.

Solo depende de ``modelo.py``. Es deliberadamente directo (fuerza bruta,
bucles simples) y no comparte código con ``costo.py``.

Decisiones: posición fuera de rango o salón inexistente cuentan una vez en
``Violaciones.salon``; sus celdas siguen contando en disponibilidad, ventana y
conflicto, pero un bloque fuera de rango se excluye de f. Tipo y capacidad se
revisan solo en salones no virtuales. λ = ``pesos.lam`` o cota + 1.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from planificador.core.modelo import Instancia, Violaciones, celdas_de


@dataclass(frozen=True)
class Reporte:
    """Resultado de validar una asignación."""

    violaciones: Violaciones
    f: float
    F: float
    problemas: list = field(default_factory=list)


def _cota(instancia: Instancia) -> float:
    """Cota superior de f: ver ``costo.cota_superior_f``."""
    w = instancia.pesos
    D = len(instancia.dias)
    H = len(instancia.franjas)
    T = len(instancia.docentes)
    G = len(instancia.grupos)
    suma_dur = 0
    suma_grupos = 0
    for b in instancia.bloques:
        suma_dur += b.duracion
        suma_grupos += len(b.grupos)
    total = w.hueco_docente * T * D * H
    total += w.hueco_grupo * G * D * H
    total += w.dispersion_docente * T * D
    total += w.carga_grupo * (G + T) * D * H
    total += w.hora_extrema * suma_dur
    total += w.cambio_sede * suma_grupos
    return float(total)


def _fuera_de_rango(instancia, bloque, pos) -> bool:
    if pos.dia < 0 or pos.dia >= len(instancia.dias):
        return True
    if pos.franja < 0:
        return True
    return pos.franja + bloque.duracion > len(instancia.franjas)


def _razon_salon_invalido(instancia, bloque, pos):
    """Texto del motivo por el que el salón es inválido, o None."""
    if _fuera_de_rango(instancia, bloque, pos):
        return (f"posición fuera de rango (día {pos.dia}, franja "
                f"{pos.franja}, duración {bloque.duracion})")
    salon = None
    for s in instancia.salones:
        if s.id == pos.salon:
            salon = s
    if salon is None:
        return f"el salón {pos.salon} no existe"
    if bloque.virtual and not salon.virtual:
        return f"bloque virtual en el salón presencial {salon.id}"
    if not bloque.virtual and salon.virtual:
        return f"bloque presencial en el salón virtual {salon.id}"
    if salon.virtual:
        return None
    if bloque.tipo_salon is not None and bloque.tipo_salon != salon.tipo:
        return (f"requiere salón de tipo {bloque.tipo_salon} y el salón "
                f"{salon.id} es de tipo {salon.tipo}")
    est = 0
    for g in instancia.grupos:
        if g.id in bloque.grupos:
            est += g.num_estudiantes
    if salon.capacidad is not None and salon.capacidad < est:
        return (f"el salón {salon.id} (capacidad {salon.capacidad}) no "
                f"alberga {est} estudiantes")
    return None


def _violaciones(instancia, asignacion, problemas) -> Violaciones:
    bloques = list(instancia.bloques)
    sin_ubicar = disponibilidad = ventana = conflicto = salon_inv = 0

    for b in bloques:
        if b.id not in asignacion:
            sin_ubicar += 1
            problemas.append(f"Bloque {b.id} sin ubicar")
    ubicados = [b for b in bloques if b.id in asignacion]

    for b in ubicados:
        pos = asignacion[b.id]
        for (d, h) in celdas_de(pos, b.duracion):
            if b.docente_id is not None:
                doc = [x for x in instancia.docentes
                       if x.id == b.docente_id][0]
                if (d, h) not in doc.disponibilidad:
                    disponibilidad += 1
                    problemas.append(
                        f"Bloque {b.id}: docente {doc.id} no disponible el "
                        f"día {d}, franja {h}")
            for gid in b.grupos:
                grupo = [x for x in instancia.grupos if x.id == gid][0]
                if (d, h) not in grupo.ventana:
                    ventana += 1
                    problemas.append(
                        f"Bloque {b.id}: grupo {gid} fuera de su ventana el "
                        f"día {d}, franja {h}")
        razon = _razon_salon_invalido(instancia, b, pos)
        if razon is not None:
            salon_inv += 1
            problemas.append(f"Bloque {b.id}: {razon}")

    for i in range(len(ubicados)):
        for j in range(i + 1, len(ubicados)):
            a, c = ubicados[i], ubicados[j]
            motivos = []
            if a.docente_id is not None and a.docente_id == c.docente_id:
                motivos.append(f"docente {a.docente_id}")
            for gid in a.grupos:
                if gid in c.grupos:
                    motivos.append(f"grupo {gid}")
            if not motivos:
                continue
            celdas_a = celdas_de(asignacion[a.id], a.duracion)
            celdas_c = celdas_de(asignacion[c.id], c.duracion)
            for celda in celdas_a:
                if celda in celdas_c:
                    conflicto += 1
                    problemas.append(
                        f"Bloques {a.id} y {c.id} se cruzan "
                        f"({', '.join(motivos)}) el día {celda[0]} "
                        f"franja {celda[1]}")

    # Choques de salón: bloques por (salón no virtual, celda).
    por_celda = {}
    for b in ubicados:
        pos = asignacion[b.id]
        salon = None
        for s in instancia.salones:
            if s.id == pos.salon:
                salon = s
        if salon is None or salon.virtual:
            continue
        for celda in celdas_de(pos, b.duracion):
            por_celda.setdefault((salon.id, celda), []).append(b.id)
    for (sid, celda), ids in sorted(por_celda.items()):
        if len(ids) > 1:
            salon_inv += len(ids) - 1
            problemas.append(
                f"Bloques {', '.join(ids)} comparten el salón {sid} el día "
                f"{celda[0]} franja {celda[1]}")
    return Violaciones(sin_ubicar, disponibilidad, ventana, conflicto,
                       salon_inv)


def _huecos_y_franjas(ocupadas_por_dia: dict):
    """(huecos, franjas ocupadas, días con clase) de una entidad."""
    huecos = franjas = dias = 0
    for lista in ocupadas_por_dia.values():
        if lista:
            dias += 1
            franjas += len(lista)
            huecos += (max(lista) - min(lista) + 1) - len(lista)
    return huecos, franjas, dias


def _f(instancia, asignacion) -> float:
    D = len(instancia.dias)
    H = len(instancia.franjas)
    validos = []
    for b in instancia.bloques:
        if b.id in asignacion:
            if not _fuera_de_rango(instancia, b, asignacion[b.id]):
                validos.append(b)

    def ocupacion(pertenece):
        """día -> lista ordenada de franjas ocupadas por la entidad."""
        res = {d: [] for d in range(D)}
        for d in range(D):
            for h in range(H):
                for b in validos:
                    if not pertenece(b):
                        continue
                    pos = asignacion[b.id]
                    if pos.dia == d and pos.franja <= h < (
                            pos.franja + b.duracion):
                        res[d].append(h)
                        break
        return res

    hueco_docente = dispersion = hueco_grupo = carga = 0
    for t in instancia.docentes:
        oc = ocupacion(lambda b, t=t: b.docente_id == t.id)
        huecos, franjas, dias = _huecos_y_franjas(oc)
        hueco_docente += huecos
        minimo_dias = -(-franjas // H)
        dispersion += max(0, dias - minimo_dias)
        if t.max_franjas_dia is not None:
            for d in range(D):
                carga += max(0, len(oc[d]) - t.max_franjas_dia)
    for g in instancia.grupos:
        oc = ocupacion(lambda b, g=g: g.id in b.grupos)
        hueco_grupo += _huecos_y_franjas(oc)[0]
        if g.max_franjas_dia is not None:
            for d in range(D):
                carga += max(0, len(oc[d]) - g.max_franjas_dia)

    extrema = 0
    for b in validos:
        for (d, h) in celdas_de(asignacion[b.id], b.duracion):
            if instancia.franjas[h].extrema:
                extrema += 1

    cambio = 0
    for g in instancia.grupos:
        for d in range(D):
            lista = []
            for b in validos:
                pos = asignacion[b.id]
                if g.id not in b.grupos or pos.dia != d or b.virtual:
                    continue
                for s in instancia.salones:
                    if s.id == pos.salon:
                        lista.append((pos.franja, b.id, s.sede))
            lista.sort()
            for k in range(len(lista) - 1):
                if lista[k][2] != lista[k + 1][2]:
                    cambio += 1

    w = instancia.pesos
    return (w.hueco_docente * hueco_docente + w.hueco_grupo * hueco_grupo
            + w.dispersion_docente * dispersion + w.carga_grupo * carga
            + w.hora_extrema * extrema + w.cambio_sede * cambio)


def validar(instancia: Instancia, asignacion: dict) -> Reporte:
    """Valida una asignación bloque_id -> Posicion y calcula v, f y F."""
    problemas: list = []
    viol = _violaciones(instancia, asignacion, problemas)
    f_val = float(_f(instancia, asignacion))
    lam = instancia.pesos.lam
    if lam is None:
        lam = _cota(instancia) + 1.0
    return Reporte(viol, f_val, f_val + lam * viol.total, problemas)
