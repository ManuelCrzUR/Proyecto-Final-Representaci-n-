"""Reparación de horarios: segundo escenario de uso del planificador.

Teoría. Un horario vigente ``X0`` deja de ser válido cuando cambian los datos
(aquí, la disponibilidad A de un docente). Replanificar desde cero produciría
un horario correcto pero muy distinto del que la comunidad ya conoce. La
*reparación* busca, en cambio, un horario factible **cercano** a ``X0``:
minimiza la perturbación (número de bloques movidos), es decir, maximiza la
*estabilidad* ``1 - movidos / ubicados_vigentes``.

Estrategia (liberación progresiva por vecindad):

1. ``bloques_invalidos`` detecta los bloques de ``X0`` que en la instancia
   nueva violan A, W, las reglas de salón o se cruzan en Γ con otro bloque.
2. Se parte de ``X0`` sin esos bloques; los demás quedan **fijos** y el solver
   (cualquiera, vía la interfaz ``Solver``) ubica solo U(X). Esto es el caso
   de perturbación mínima: solo se mueve lo estrictamente inválido.
3. Si el resultado no es meta (v > 0), es probable que los bloques fijos
   bloqueen a los inválidos. Se liberan también los vecinos en Γ (radio 1 y
   luego 2) de los bloques sin ubicar o inválidos y se reintenta: se agranda
   el subproblema solo lo necesario (búsqueda de vecindad creciente, como en
   LNS). Se devuelve el mejor intento por F.

Presupuesto: ``limites.max_segundos`` es global; cada intento recibe el
tiempo restante dividido entre los intentos que aún podrían ejecutarse.
``max_nodos`` se aplica por intento.

Traza. La traza devuelta concatena las trazas de todos los intentos (pasos
renumerados, un único evento ``fin`` final) y, para que la reproducción
(``reproduccion.cuadros``) sea coherente sin ``asignacion_final``:

* Al iniciar cada intento se registra un evento ``expandir`` con la foto del
  estado inicial de ese intento (vigente menos los bloques liberados). Se usa
  ``expandir`` porque ese estado es la raíz que el solver empieza a expandir
  y porque, como en A*/avara/beam, ``expandir`` con ``asignacion`` reemplaza
  el estado mostrado; así los ``add``/``del`` del solver parten de la base
  correcta en cada intento.
* Justo antes de ``fin`` se registra un evento ``mejora`` con la foto de la
  asignación devuelta ("se conserva el intento de radio r"), de modo que el
  último cuadro es exactamente ``Resultado.asignacion``. Este evento no se
  pierde aunque la traza esté truncada: se amplía el tope en uno solo para él.
"""

from __future__ import annotations

import time
from dataclasses import replace

from planificador.core.conflictos import construir_conflictos
from planificador.core.estado import Estado
from planificador.core.modelo import Instancia, celdas_de

from .base import Limites, Resultado, Solver, Traza, foto


def _salon_ilegal(instancia: Instancia, bloque, pos) -> bool:
    """True si la posición es ilegal por forma o por reglas de salón."""
    if not 0 <= pos.dia < instancia.num_dias:
        return True
    if pos.franja < 0 or pos.franja + bloque.duracion > instancia.num_franjas:
        return True
    salon = instancia.salon.get(pos.salon)
    if salon is None:
        return True
    if bloque.virtual != salon.virtual:
        return True
    if salon.virtual:
        return False
    if bloque.tipo_salon is not None and bloque.tipo_salon != salon.tipo:
        return True
    return (salon.capacidad is not None
            and salon.capacidad < instancia.estudiantes(bloque.id))


def _viola_unarias(instancia: Instancia, bloque, pos) -> bool:
    """True si alguna celda del bloque viola A (docente) o W (grupo)."""
    celdas = celdas_de(pos, bloque.duracion)
    if bloque.docente_id is not None:
        disp = instancia.docente[bloque.docente_id].disponibilidad
        if any(c not in disp for c in celdas):
            return True
    for g in bloque.grupos:
        ventana = instancia.grupo[g].ventana
        if any(c not in ventana for c in celdas):
            return True
    return False


def bloques_invalidos(instancia: Instancia, asignacion: dict) -> frozenset:
    """Bloques ubicados que en ``instancia`` dejan de ser válidos.

    Un bloque es inválido si, en su posición actual, viola A (disponibilidad
    del docente), W (ventana del grupo), una regla de salón (tipo, capacidad,
    modalidad, fuera de rango o salón inexistente) o se cruza en Γ con otro
    bloque ubicado. En un cruce se marca **solo uno**: se recorren los
    bloques en orden de id y se marca el de id mayor del par, salvo que su
    vecino ya sea inválido por otra causa (entonces el cruce desaparece al
    liberarlo). Así se libera lo mínimo y de forma determinista. Los bloques
    de ``asignacion`` que no existen en la instancia se ignoran.
    """
    ubicados = {b: p for b, p in asignacion.items()
                if b in instancia.bloque}
    invalidos: set = set()
    for bid in sorted(ubicados):
        b = instancia.bloque[bid]
        if (_salon_ilegal(instancia, b, ubicados[bid])
                or _viola_unarias(instancia, b, ubicados[bid])):
            invalidos.add(bid)
    gamma = construir_conflictos(instancia)
    celdas = {bid: set(celdas_de(ubicados[bid], instancia.bloque[bid].duracion))
              for bid in ubicados if bid not in invalidos}
    for bid in sorted(celdas):
        for otro in gamma[bid]:
            if otro < bid and otro in celdas and otro not in invalidos:
                if celdas[bid] & celdas[otro]:
                    invalidos.add(bid)
                    break
    return frozenset(invalidos)


def _estado_sin(instancia, vigente: dict, liberados: set) -> tuple:
    """Estado con ``vigente`` menos ``liberados``; quita también los que
    chocan en salón (en orden de id). Devuelve ``(estado, extra_liberados)``.
    """
    estado = Estado(instancia)
    extra: set = set()
    for bid in sorted(vigente):
        if bid in liberados or bid not in instancia.bloque:
            continue
        try:
            estado._colocar(bid, vigente[bid])
        except ValueError:
            extra.add(bid)
    return estado, extra


def _vecindad(gamma: dict, semillas, radio: int) -> set:
    """Bloques a distancia <= radio en Γ de las semillas (incluye semillas)."""
    visto = set(semillas)
    frontera = set(semillas)
    for _ in range(radio):
        frontera = {v for u in frontera for v in gamma[u]} - visto
        visto |= frontera
    return visto


def _unir_trazas(intentos: list, limites: Limites, mejor_radio: int,
                 mejor_asignacion: dict) -> Traza:
    """Concatena las trazas de los intentos renumerando pasos.

    ``intentos`` es una lista de ``(radio, liberados, estado_inicial, traza)``.
    Antes de los eventos de cada intento se inserta un ``expandir`` con la
    foto de su estado inicial. Al final se agrega un ``mejora`` con la foto de
    ``mejor_asignacion`` y un único ``fin``. El evento de sincronización final
    se registra con el tope ampliado en uno para que nunca se pierda.
    """
    nueva = Traza(limites.max_eventos_traza)
    ultimo_fin = ""
    for k, (radio, n_lib, inicial, t) in enumerate(intentos, start=1):
        nueva.registrar(
            "expandir", asignacion=foto(inicial),
            nota=f"intento {k} (radio {radio}): se liberan {n_lib} bloques")
        for ev in t.eventos:
            if ev.tipo == "fin":
                ultimo_fin = ev.nota
                continue
            datos = {k2: getattr(ev, k2) for k2 in (
                "bloque", "posicion", "F", "v", "f", "tam_frontera",
                "profundidad", "asignacion", "nota")}
            nueva.registrar(ev.tipo, **datos)
        nueva.descartados += t.descartados
    nueva.max_eventos += 1
    nueva.registrar(
        "mejora", asignacion=foto(mejor_asignacion),
        nota=f"se conserva el intento de radio {mejor_radio}")
    nueva.registrar("fin", nota=ultimo_fin)
    return nueva


def reparar(instancia: Instancia, asignacion_vigente: dict, solver: Solver,
            limites: Limites = Limites(), radio_max: int = 2) -> Resultado:
    """Repara ``asignacion_vigente`` en la instancia nueva con ``solver``.

    Ver el docstring del módulo para la estrategia. ``extra`` del resultado:
    ``invalidos``, ``liberados`` (total de bloques liberados en el último
    intento), ``movidos`` (bloques vigentes cuya posición final difiere o que
    quedaron sin ubicar), ``radio`` (radio del mejor intento), ``intentos``
    y ``estabilidad``. No muta ``asignacion_vigente``.
    """
    inicio = time.perf_counter()
    vigente = dict(asignacion_vigente)
    gamma = construir_conflictos(instancia)
    invalidos = bloques_invalidos(instancia, vigente)
    resultados: list = []
    radio = 0
    liberados = set(invalidos)
    liberados_final = 0
    while True:
        estado, extra = _estado_sin(instancia, vigente, liberados)
        liberados |= extra
        restante = None
        if limites.max_segundos is not None:
            restante = max(0.0, limites.max_segundos
                           - (time.perf_counter() - inicio))
            restante /= (radio_max - radio + 1)
        lim = replace(limites, max_segundos=restante)
        # Foto antes de resolver: el solver puede mutar el estado recibido.
        inicial_intento = dict(estado.asignacion)
        res = solver.resolver(instancia, estado, lim)
        resultados.append((radio, len(liberados), res, inicial_intento))
        if res.exito or radio >= radio_max:
            break
        if (limites.max_segundos is not None
                and time.perf_counter() - inicio >= limites.max_segundos):
            break
        semillas = set(invalidos) | {
            b.id for b in instancia.bloques if b.id not in res.asignacion}
        radio += 1
        liberados |= _vecindad(gamma, semillas, radio) & set(vigente)
    liberados_final = resultados[-1][1]
    r_mejor, _, mejor, _ = min(resultados, key=lambda t: (t[2].F, t[0]))
    movidos = sum(1 for b, p in vigente.items()
                  if b in instancia.bloque and mejor.asignacion.get(b) != p)
    ubicados = len(vigente)
    traza = _unir_trazas(
        [(r, n, ini, res.traza) for r, n, res, ini in resultados],
        limites, r_mejor, mejor.asignacion)
    extra_res = dict(mejor.extra)
    extra_res.update({
        "invalidos": len(invalidos),
        "liberados": liberados_final,
        "movidos": movidos,
        "radio": r_mejor,
        "intentos": len(resultados),
        "estabilidad": 1 - movidos / ubicados if ubicados else 1.0,
    })
    return replace(
        mejor,
        algoritmo=f"reparacion+{solver.nombre}",
        tiempo_s=time.perf_counter() - inicio,
        nodos_expandidos=sum(t[2].nodos_expandidos for t in resultados),
        nodos_generados=sum(t[2].nodos_generados for t in resultados),
        traza=traza,
        extra=extra_res,
    )
