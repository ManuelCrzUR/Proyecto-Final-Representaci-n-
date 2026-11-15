"""Generador reproducible de instancias sintéticas y escenario de reparación.

Defaults proporcionales al tamaño ``n`` (``n_bloques``) cuando no se indican:

* docentes = ``max(2, n // 5)``
* grupos   = ``max(2, n // 8)``
* salones presenciales = ``max(2, n // 10)`` más un salón virtual ``SV``.
  El primer ``AULA`` y el primer ``LAB`` son "salones grandes" (capacidad 80),
  de modo que todo bloque presencial tiene al menos un salón compatible.

Con ``garantizar_factible`` se construye primero una solución oculta (bloques
en orden aleatorio, en posiciones legales sin choques de docente ni de grupo)
y la disponibilidad de docentes y la ventana de grupos se definen como las
celdas usadas por esa solución más celdas aleatorias. Si algún bloque no cabe
se reintenta con otra sub-semilla (máx. 50 intentos); si se agotan, se añade
un salón presencial y se vuelve a intentar (máx. 5 ampliaciones).
Todo el azar sale de ``random.Random`` con semillas derivadas: es determinista.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import replace
from pathlib import Path
from typing import Optional

from planificador.core.acciones import posiciones_legales, aplicar_en_sitio
from planificador.core.estado import Estado
from planificador.core.modelo import (
    Anadir, Bloque, Dia, Docente, Franja, Grupo, Instancia, Pesos, Posicion,
    Salon, celdas_de)

MAX_INTENTOS = 50
MAX_AMPLIACIONES = 5
RAIZ = Path(__file__).resolve().parents[2]


def _crear_salones(rng: random.Random, n_pres: int) -> tuple:
    """Salones presenciales (AULA mayoría, LAB ~25 %) más el virtual."""
    n_lab = max(1, n_pres // 4)
    salones = []
    for i in range(n_pres):
        lab = i >= n_pres - n_lab
        grande = i in (0, n_pres - n_lab)
        cap = 80 if grande else rng.randint(20, 60)
        salones.append(Salon(id=f"S{i + 1:02d}", tipo="LAB" if lab else "AULA",
                             capacidad=cap, virtual=False,
                             sede="A" if rng.random() < 0.6 else "B"))
    salones.append(Salon(id="SV", tipo="VIRTUAL", capacidad=None,
                         virtual=True, sede=""))
    return tuple(salones)


def _crear_bloques(rng, n, ids_docentes, grupos, duracion_max, prob_virtual):
    """Bloques con duración sesgada a cortas, 1-2 grupos, docente o None."""
    pesos_dur = [2 ** (duracion_max - d) for d in range(1, duracion_max + 1)]
    ids_grupos = [g.id for g in grupos]
    bloques = []
    for i in range(n):
        dur = rng.choices(range(1, duracion_max + 1), weights=pesos_dur)[0]
        k = 2 if (len(ids_grupos) > 1 and rng.random() < 0.1) else 1
        gs = tuple(sorted(rng.sample(ids_grupos, k)))
        doc = None if rng.random() < 0.05 else rng.choice(ids_docentes)
        virtual = rng.random() < prob_virtual
        lab = (not virtual) and rng.random() < 0.2
        bloques.append(Bloque(
            id=f"B{i + 1:03d}", modulo_id=f"M{rng.randint(1, max(1, n // 3))}",
            duracion=dur, grupos=gs, docente_id=doc,
            tipo_sesion="PRACTICA" if lab else "TEORIA",
            tipo_salon="LAB" if lab else None, virtual=virtual))
    return bloques


def _ajustar_compatibilidad(bloques, salones, grupos) -> list:
    """Quita ``tipo_salon`` o la capacidad exigida si no hay salón compatible."""
    num = {g.id: g.num_estudiantes for g in grupos}
    res = []
    for b in bloques:
        if b.virtual:
            res.append(b)
            continue
        est = sum(num[g] for g in b.grupos)
        ok = [s for s in salones if not s.virtual
              and (b.tipo_salon is None or b.tipo_salon == s.tipo)
              and (s.capacidad is None or s.capacidad >= est)]
        if not ok:
            b = replace(b, tipo_salon=None, tipo_sesion="TEORIA")
        res.append(b)
    return res


def _celdas_todas(num_dias: int, num_franjas: int) -> list:
    return [(d, h) for d in range(num_dias) for h in range(num_franjas)]


def _solucion_oculta(inst: Instancia, rng: random.Random) -> Optional[dict]:
    """Coloca todos los bloques sin choques de docente ni de grupo."""
    est = Estado(inst)
    orden = [b.id for b in inst.bloques]
    rng.shuffle(orden)
    # Primero los bloques más largos: más difíciles de colocar.
    orden.sort(key=lambda b: -inst.bloque[b].duracion)
    for bid in orden:
        b = inst.bloque[bid]
        validas = []
        for pos in posiciones_legales(est, bid):
            cs = celdas_de(pos, b.duracion)
            if b.docente_id is not None and any(
                    est.ocupacion_docente(b.docente_id, c) for c in cs):
                continue
            if any(est.ocupacion_grupo(g, c) for g in b.grupos for c in cs):
                continue
            validas.append(pos)
        if not validas:
            return None
        aplicar_en_sitio(est, Anadir(bid, rng.choice(validas)))
    return dict(est.asignacion)


def _rellenar(rng, base: set, todas: list, prob: float) -> frozenset:
    extra = {c for c in todas if rng.random() < prob}
    return frozenset(base | extra)


def generar_instancia(
        n_bloques: int, semilla: int, *, num_dias: int = 6,
        num_franjas: int = 8, num_salones: Optional[int] = None,
        num_docentes: Optional[int] = None, num_grupos: Optional[int] = None,
        prob_disponible: float = 0.5, prob_ventana: float = 0.7,
        prob_virtual: float = 0.1, duracion_max: int = 3,
        garantizar_factible: bool = True, pesos: Optional[Pesos] = None,
        nombre: Optional[str] = None) -> tuple:
    """Genera ``(instancia, solucion_oculta | None)`` de forma determinista.

    Misma semilla y parámetros producen una instancia idéntica. Ver el
    docstring del módulo para las fórmulas por defecto y la estrategia de
    factibilidad.
    """
    n = n_bloques
    nd = num_docentes if num_docentes is not None else max(2, n // 5)
    ng = num_grupos if num_grupos is not None else max(2, n // 8)
    ns = num_salones if num_salones is not None else max(2, n // 10)
    nombre = nombre or f"sint_{n}_{semilla}"
    pesos = pesos or Pesos()
    duracion_max = max(1, min(duracion_max, num_franjas))
    todas = _celdas_todas(num_dias, num_franjas)
    dias = tuple(Dia(indice=i, semana=i // 6, dia_semana=i % 6)
                 for i in range(num_dias))
    franjas = tuple(
        Franja(id=f"H{h + 1:02d}", inicio=420 + 60 * h, fin=480 + 60 * h,
               extrema=(h in (0, num_franjas - 1)))
        for h in range(num_franjas))
    ids_doc = [f"T{i + 1:02d}" for i in range(nd)]

    ampliaciones = 0
    intento = 0
    while True:
        rng = random.Random(semilla * 1000003 + intento * 101 + ampliaciones)
        salones = _crear_salones(rng, ns + ampliaciones)
        grupos = tuple(
            Grupo(id=f"G{i + 1:02d}", num_estudiantes=rng.randint(10, 35))
            for i in range(ng))
        bloques = _crear_bloques(rng, n, ids_doc, grupos, duracion_max,
                                 prob_virtual)
        bloques = tuple(_ajustar_compatibilidad(bloques, salones, grupos))

        def armar(docs, grs):
            return Instancia(dias=dias, franjas=franjas, salones=salones,
                             docentes=docs, grupos=grs, bloques=bloques,
                             pesos=pesos, nombre=nombre)

        if not garantizar_factible:
            docs = tuple(Docente(id=i, nombre=f"Docente {i}",
                                 disponibilidad=_rellenar(
                                     rng, set(), todas, prob_disponible))
                         for i in ids_doc)
            grs = tuple(replace(g, ventana=_rellenar(
                rng, set(), todas, prob_ventana)) for g in grupos)
            return armar(docs, grs), None

        todo = frozenset(todas)
        prelim = armar(
            tuple(Docente(id=i, disponibilidad=todo) for i in ids_doc),
            tuple(replace(g, ventana=todo) for g in grupos))
        sol = _solucion_oculta(prelim, rng)
        if sol is not None:
            uso_d = {i: set() for i in ids_doc}
            uso_g = {g.id: set() for g in grupos}
            for bid, pos in sol.items():
                b = prelim.bloque[bid]
                cs = celdas_de(pos, b.duracion)
                if b.docente_id is not None:
                    uso_d[b.docente_id].update(cs)
                for g in b.grupos:
                    uso_g[g].update(cs)
            docs = tuple(Docente(id=i, nombre=f"Docente {i}",
                                 disponibilidad=_rellenar(
                                     rng, uso_d[i], todas, prob_disponible))
                         for i in ids_doc)
            grs = tuple(replace(g, ventana=_rellenar(
                rng, uso_g[g.id], todas, prob_ventana)) for g in grupos)
            return armar(docs, grs), sol
        intento += 1
        if intento >= MAX_INTENTOS:
            intento = 0
            ampliaciones += 1
            if ampliaciones > MAX_AMPLIACIONES:
                raise RuntimeError("No se pudo generar una instancia factible")


def perturbar_disponibilidad(
        instancia: Instancia, solucion: dict, semilla: int, *,
        num_docentes: int = 1, fraccion: float = 0.5) -> Instancia:
    """Quita celdas usadas por la solución a ``num_docentes`` docentes.

    La solución vigente deja de ser válida (v > 0). El resto no cambia.
    """
    rng = random.Random(semilla)
    uso: dict = {}
    for bid, pos in solucion.items():
        b = instancia.bloque[bid]
        if b.docente_id is not None:
            uso.setdefault(b.docente_id, set()).update(
                celdas_de(pos, b.duracion))
    candidatos = sorted(uso)
    elegidos = rng.sample(candidatos, min(num_docentes, len(candidatos)))
    nuevos = []
    for d in instancia.docentes:
        if d.id in elegidos:
            celdas = sorted(uso[d.id])
            k = max(1, math.ceil(fraccion * len(celdas)))
            quitar = set(rng.sample(celdas, min(k, len(celdas))))
            d = replace(d, disponibilidad=d.disponibilidad - quitar)
        nuevos.append(d)
    return replace(instancia, docentes=tuple(nuevos),
                   nombre=f"{instancia.nombre}-perturbada")


def guardar_json(instancia: Instancia, ruta, solucion=None) -> None:
    """Guarda la instancia (y opcionalmente la solución) en JSON."""
    datos = {"instancia": instancia.a_dict(), "solucion": None}
    if solucion is not None:
        datos["solucion"] = {b: [p.dia, p.franja, p.salon]
                             for b, p in solucion.items()}
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    # ``a_dict`` deja frozensets dentro de las listas de entidades; se
    # convierten aquí a listas ordenadas de celdas.
    ruta.write_text(
        json.dumps(datos, ensure_ascii=False, indent=1,
                   default=lambda x: sorted(list(c) for c in x)),
        encoding="utf-8")


def cargar_json(ruta) -> tuple:
    """Inversa de ``guardar_json``: ``(instancia, solucion | None)``."""
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    inst = Instancia.desde_dict(datos["instancia"])
    sol = datos.get("solucion")
    if sol is not None:
        sol = {b: Posicion(int(p[0]), int(p[1]), p[2])
               for b, p in sol.items()}
    return inst, sol


def main(argv=None) -> int:
    """CLI: genera una instancia sintética y la guarda en JSON."""
    ap = argparse.ArgumentParser(description="Genera una instancia sintética")
    ap.add_argument("--bloques", type=int, default=50)
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--salida", default=None)
    args = ap.parse_args(argv)
    inst, sol = generar_instancia(args.bloques, args.semilla)
    salida = Path(args.salida) if args.salida else (
        RAIZ / "salidas" / "instancias"
        / f"sint_{args.bloques}_{args.semilla}.json")
    guardar_json(inst, salida, sol)
    print(f"Instancia {inst.nombre}: {len(inst.bloques)} bloques, "
          f"{len(inst.docentes)} docentes, {len(inst.grupos)} grupos, "
          f"{len(inst.salones)} salones, {inst.num_dias}x{inst.num_franjas} "
          f"celdas; solución oculta: {len(sol)} bloques ubicados")
    print(f"Guardada en {salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
