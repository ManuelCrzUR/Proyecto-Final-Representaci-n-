"""Búsqueda informada: nodo, costo de camino g, heurística h, A* y avara.

Teoría
------
Una búsqueda informada ordena la frontera con una función de evaluación que
usa conocimiento del problema. Aquí el espacio de estados es el árbol de
decisiones: cada nivel decide UN bloque (variable elegida con MRV), ya sea
ubicándolo en una posición de su dominio consistente o "saltándolo" (queda en
U(X) y cuesta λ). Una *hoja* es un nodo sin bloques por decidir.

Costo de camino g (contrato, Sprint 3)::

    g(n) = λ·[v_disp + v_vent + v_conf + #saltados](n)
           + w_ext·φ_extrema(n) + w_carga·φ_carga(n)

* **g es aditivo y monótono.** Cada término es una suma sobre bloques ya
  decididos (o, para la carga, una suma de excesos ``max(0, n_ocupadas - tope)``
  que solo crece al añadir franjas). Decidir un bloque más nunca baja ningún
  término, luego el costo de paso c(n, n') = g(n') - g(n) es >= 0. Eso es lo
  que necesita A* (sin costos negativos, f no decrece por el camino).
* **Huecos, dispersión y cambio de sede NO son aditivos.** Un bloque que se
  ubica después puede *rellenar* un hueco (baja φ_hueco), reducir los días con
  clase (baja la dispersión) o quedar entre dos clases de la misma sede
  (baja los cambios de sede). Su contribución marginal puede ser negativa,
  así que g dejaría de ser monótono y h dejaría de ser admisible. Por eso no
  entran en g: se evalúan al final con F completo (``comun.resultado_desde``)
  y se reportan.

Heurística h::

    h(n) = Σ_{m no decidido} t(m),  t(m) = λ            si dom_cons(m) = ∅
                                     t(m) = min(λ, w_ext·min_{p∈dom_cons(m)} ext(p))

con ``ext(p)`` el número de franjas extremas que ocupa el bloque en p.

* **Admisible** (h(n) <= costo real restante h*(n)): todo bloque no decidido
  deberá ubicarse en una posición que hoy está en su dominio consistente (los
  dominios solo se encogen al ubicar otros bloques) o saltarse. Si el dominio
  es vacío solo queda saltarlo (λ). Si no, cuesta al menos
  ``w_ext·min ext`` si se ubica, o λ si se salta: el mínimo de ambos es cota
  inferior. Los términos de bloques distintos son independientes y sus costos
  futuros se suman en g, luego la suma es cota inferior. (Se incluye el
  ``min`` con λ para ser admisible incluso con λ manual pequeño.)
* **Consistente** (h(n) <= c(n, n') + h(n')): al decidir el bloque b, su
  término t(b) desaparece de h, pero el paso cuesta >= t(b) (λ si se salta,
  >= w_ext·ext(p) >= t(b) si se ubica), y los términos de los demás bloques
  no bajan (dominios que solo se encogen). Consistente implica admisible y
  que f = g + h no decrece a lo largo de un camino.

Implementación incremental de h: en cada hijo solo se recalculan los términos
de los vecinos de Γ del bloque ubicado (su dominio es el único que cambia por
conflicto de docente/grupo); los demás términos se conservan del padre. Es una
cota inferior algo más débil que la h exacta (ignora que ocupar un salón puede
vaciar dominios de bloques no vecinos), pero sigue siendo admisible y
consistente y es mucho más barata. ``heuristica(estado, no_decididos)`` calcula
la h exacta desde cero (se usa en la raíz y en los tests).

Completitud y optimalidad de A*
-------------------------------
El árbol es finito (profundidad = |U|) y siempre existe el hijo "saltar", así
que ninguna rama muere: **A\\* es completo**. Con h admisible (y consistente)
la primera hoja extraída de la frontera minimiza g sobre todas las hojas:
**A\\* es óptimo respecto de g**. (Si todo nodo con f < C* se expande antes de
extraer una hoja con g = C*.) El precio es tiempo y memoria exponenciales: la
frontera crece con el factor de ramificación (|dominio|, decenas o cientos).
Con ``peso_h > 1`` (A* ponderado) se pierde la garantía de optimalidad (el
costo queda a lo sumo en un factor peso_h del óptimo si h es admisible) pero
se expande mucho menos. La avara (f = h + distancia, no admisible) tampoco
es óptima ni garantiza nada
sobre g; solo es completa aquí por la opción "saltar".

Estados repetidos: como la variable de cada nodo es función determinista del
estado (MRV con desempate fijo), dos caminos distintos que llegan al mismo
conjunto (asignación, saltados) tendrían que bifurcar en un mismo nodo con
distinta decisión, y eso da conjuntos distintos. Es decir, el espacio es un
ÁRBOL y la detección de repetidos casi nunca descarta algo; se mantiene
(``detectar_repetidos=True``) por rigor, con clave
``(frozenset(asignación), frozenset(saltados))``.

Trazas: el evento ``expandir`` lleva ``asignacion=foto(...)`` del nodo
expandido y ``F`` = f del algoritmo (g + peso_h·h en A*, h en avara), no el F
del core; ``frontera`` se registra cada ``CADA_FRONTERA`` expansiones.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Optional

from planificador.core import costo
from planificador.core.conflictos import construir_conflictos
from planificador.core.estado import Estado
from planificador.core.modelo import celdas_de

from .base import Limites, Presupuesto, Solver, Traza, foto
from .comun import dominio_consistente, elegir_mrv, resultado_desde

CADA_FRONTERA = 50


# --------------------------------------------------------------------------
# Costo de camino g (desde cero) y heurística h (exacta)
# --------------------------------------------------------------------------

def costo_camino(instancia, asignacion, saltados) -> float:
    """g desde cero sobre una asignación parcial (incluye bloques fijos).

    ``saltados``: colección de bloques decididos como "no ubicar". NO se
    cuentan los demás bloques de U (aún no decididos).
    """
    lam = costo.lam(instancia)
    viol = costo._violaciones_de(instancia, asignacion)
    phi = costo._desglose_de(instancia, asignacion)
    w = instancia.pesos
    duros = (viol.disponibilidad + viol.ventana + viol.conflicto
             + viol.salon + len(set(saltados)))
    return (lam * duros + w.hora_extrema * phi["hora_extrema"]
            + w.carga_grupo * phi["carga_grupo"])


def _prefijo_extremas(instancia) -> list:
    cache = instancia.__dict__
    if "_pref_ext_informada" not in cache:
        pref = [0]
        for fr in instancia.franjas:
            pref.append(pref[-1] + (1 if fr.extrema else 0))
        cache["_pref_ext_informada"] = pref
    return cache["_pref_ext_informada"]


def _extremas(instancia, franja: int, duracion: int) -> int:
    pref = _prefijo_extremas(instancia)
    return pref[franja + duracion] - pref[franja]


def _termino(lam: float, w_ext: float, min_ext: Optional[int]) -> float:
    """t(m): λ si el dominio es vacío; si no min(λ, w_ext·min ext)."""
    if min_ext is None:
        return lam
    return min(lam, w_ext * min_ext)


def _terminos(estado, doms: dict) -> dict:
    inst = estado.instancia
    lam = costo.lam(inst)
    w_ext = inst.pesos.hora_extrema
    out = {}
    for m, dom in doms.items():
        dur = inst.bloque[m].duracion
        mn = min((_extremas(inst, p.franja, dur) for p in dom), default=None)
        out[m] = _termino(lam, w_ext, mn)
    return out


def heuristica(estado, no_decididos) -> float:
    """h exacta (desde cero) de un estado y sus bloques no decididos."""
    doms = {m: dominio_consistente(estado, m) for m in no_decididos}
    return sum(_terminos(estado, doms).values())


# --------------------------------------------------------------------------
# Nodo y contexto
# --------------------------------------------------------------------------

@dataclass(eq=False)
class Nodo:
    """Nodo ligero: guarda solo la última decisión y el puntero al padre.

    ``pos is None`` significa "saltar el bloque". La asignación completa se
    reconstruye con ``Contexto.asignacion_de`` (profundidad <= |U|).
    """

    padre: Optional["Nodo"]
    bloque: Optional[str]
    pos: object
    g: float
    h: float
    prof: int
    n_saltados: int = 0
    restr: int = 0  # desempate: posiciones de vecinos eliminadas por la decisión


class Contexto:
    """Datos de una resolución: instancia, bloques fijos y Γ."""

    def __init__(self, instancia, estado_inicial=None):
        self.instancia = instancia
        estado = estado_inicial if estado_inicial is not None \
            else Estado(instancia)
        self.base = dict(estado.asignacion)
        self.pendientes = frozenset(estado.sin_ubicar())
        self.conflictos = construir_conflictos(instancia)
        self.lam = costo.lam(instancia)
        self.w_ext = instancia.pesos.hora_extrema
        self.w_carga = instancia.pesos.carga_grupo
        self.total = len(self.pendientes)

    def es_hoja(self, nodo) -> bool:
        return nodo.prof == self.total

    def decisiones_de(self, nodo) -> list:
        """Decisiones desde la raíz: lista de (bloque, pos | None)."""
        cadena = []
        while nodo.padre is not None:
            cadena.append((nodo.bloque, nodo.pos))
            nodo = nodo.padre
        cadena.reverse()
        return cadena

    def asignacion_de(self, nodo) -> dict:
        asig = dict(self.base)
        for b, p in self.decisiones_de(nodo):
            if p is not None:
                asig[b] = p
        return asig

    def saltados_de(self, nodo) -> frozenset:
        return frozenset(b for b, p in self.decisiones_de(nodo) if p is None)

    def estado_de(self, nodo) -> Estado:
        return Estado(self.instancia, self.asignacion_de(nodo))

    def no_decididos_de(self, nodo) -> frozenset:
        return self.pendientes - {b for b, _ in self.decisiones_de(nodo)}

    def clave(self, nodo) -> tuple:
        """Clave de estado repetido: (asignación, saltados)."""
        asig = frozenset(self.asignacion_de(nodo).items())
        return asig, self.saltados_de(nodo)

    def raiz(self) -> Nodo:
        est = Estado(self.instancia, self.base)
        g0 = costo_camino(self.instancia, self.base, ())
        return Nodo(None, None, None, g0, heuristica(est, self.pendientes), 0)


# --------------------------------------------------------------------------
# Incremento de g y sucesores
# --------------------------------------------------------------------------

def _delta_carga(estado, b, pos) -> int:
    inst = estado.instancia
    H = inst.num_franjas
    entidades = []
    if b.docente_id is not None:
        entidades.append((b.docente_id,
                          inst.docente[b.docente_id].max_franjas_dia,
                          estado.ocupacion_docente))
    for g in b.grupos:
        entidades.append((g, inst.grupo[g].max_franjas_dia,
                          estado.ocupacion_grupo))
    total = 0
    for ent, tope, ocup in entidades:
        if tope is None:
            continue
        actuales = sum(1 for h in range(H) if ocup(ent, (pos.dia, h)) > 0)
        nuevas = sum(1 for h in range(pos.franja, pos.franja + b.duracion)
                     if ocup(ent, (pos.dia, h)) == 0)
        total += max(0, actuales + nuevas - tope) - max(0, actuales - tope)
    return total


def delta_g(ctx: Contexto, estado, bloque_id: str, pos) -> float:
    """Δg exacto al ubicar ``bloque_id`` en ``pos`` sobre ``estado``.

    Suma: λ·(disp + vent + conflictos nuevos) + w_ext·extremas + w_carga·Δcarga.
    Si ``pos`` es None (saltar) vale λ.
    """
    if pos is None:
        return ctx.lam
    inst = ctx.instancia
    b = inst.bloque[bloque_id]
    celdas = celdas_de(pos, b.duracion)
    duros = 0
    if b.docente_id is not None:
        disp = inst.docente[b.docente_id].disponibilidad
        duros += sum(1 for c in celdas if c not in disp)
    for g in b.grupos:
        vent = inst.grupo[g].ventana
        duros += sum(1 for c in celdas if c not in vent)
    vecinos = ctx.conflictos[bloque_id]
    for c in celdas:
        duros += len(estado.bloques_en(c) & vecinos)
    return (ctx.lam * duros
            + ctx.w_ext * _extremas(inst, pos.franja, b.duracion)
            + ctx.w_carga * _delta_carga(estado, b, pos))


def _termino_vecino(ctx, slots_dia, dur_c, dia, f0, dur_b) -> tuple:
    """(t(c), #celdas eliminadas) de un vecino tras ubicar b en (dia, f0).

    ``slots_dia``: día -> lista de (franja, extremas) de las celdas
    (dia, franja) del dominio de c (sin repetir salones).
    """
    mejor = None
    quitadas = 0
    for d, lista in slots_dia.items():
        for f, ext in lista:
            if d == dia and f < f0 + dur_b and f0 < f + dur_c:
                quitadas += 1  # se traslapa con b: sale del dominio
                continue
            if mejor is None or ext < mejor:
                mejor = ext
    return _termino(ctx.lam, ctx.w_ext, mejor), quitadas


def sucesores(ctx: Contexto, nodo: Nodo, estado=None) -> list:
    """Hijos de ``nodo``: una posición consistente de la variable MRV o saltar.

    Decisión de diseño: los valores son el ``dominio_consistente`` (no solo el
    unario), así g solo crece por saltos y por términos blandos monótonos; el
    espacio resultante cubre todas las asignaciones donde cada bloque queda
    ubicado de forma consistente o saltado. Los hijos salen en el orden
    determinista de ``posiciones_legales`` y al final el hijo "saltar".
    """
    if ctx.es_hoja(nodo):
        return []
    inst = ctx.instancia
    if estado is None:
        estado = ctx.estado_de(nodo)
    nd = ctx.no_decididos_de(nodo)
    doms = {m: dominio_consistente(estado, m) for m in nd}
    terminos = _terminos(estado, doms)
    suma = sum(terminos.values())
    var = elegir_mrv(doms, ctx.conflictos)
    b = inst.bloque[var]
    vecinos = [c for c in ctx.conflictos[var] if c in doms]
    slots = {}
    for c in vecinos:
        por_dia: dict = {}
        vistos = set()
        dur_c = inst.bloque[c].duracion
        for p in doms[c]:
            if (p.dia, p.franja) in vistos:
                continue
            vistos.add((p.dia, p.franja))
            por_dia.setdefault(p.dia, []).append(
                (p.franja, _extremas(inst, p.franja, dur_c)))
        slots[c] = por_dia
    base_h = suma - terminos[var]
    hijos = []
    cache_vec: dict = {}
    for p in doms[var]:
        clave = (p.dia, p.franja)
        if clave not in cache_vec:
            dh = quitadas = 0
            for c in vecinos:
                t, q = _termino_vecino(ctx, slots[c], inst.bloque[c].duracion,
                                       p.dia, p.franja, b.duracion)
                dh += t - terminos[c]
                quitadas += q
            cache_vec[clave] = (dh, quitadas)
        dh, quitadas = cache_vec[clave]
        hijos.append(Nodo(nodo, var, p, nodo.g + delta_g(ctx, estado, var, p),
                          base_h + dh, nodo.prof + 1, nodo.n_saltados,
                          quitadas))
    hijos.append(Nodo(nodo, var, None, nodo.g + ctx.lam, base_h,
                      nodo.prof + 1, nodo.n_saltados + 1))
    return hijos


def mejor_visto(a: Optional[Nodo], b: Nodo) -> Nodo:
    """El más profundo; desempate por menor g."""
    if a is None or (b.prof, -b.g) > (a.prof, -a.g):
        return b
    return a


# --------------------------------------------------------------------------
# Solvers
# --------------------------------------------------------------------------

class _Informada(Solver):
    """Búsqueda de mejor-primero genérica; subclases fijan la prioridad."""

    nombre = "informada"

    def __init__(self, peso_h: float = 1.0, detectar_repetidos: bool = True):
        super().__init__(peso_h=peso_h, detectar_repetidos=detectar_repetidos)
        self.peso_h = peso_h
        self.detectar_repetidos = detectar_repetidos

    def _f(self, nodo: Nodo) -> float:
        raise NotImplementedError

    def _clave(self, nodo: Nodo, contador: int) -> tuple:
        raise NotImplementedError

    def resolver(self, instancia, estado_inicial=None,
                 limites: Limites = Limites()):
        pres = Presupuesto(limites)
        traza = Traza(limites.max_eventos_traza)
        ctx = Contexto(instancia, estado_inicial)
        self._total = ctx.total
        self._lam = ctx.lam
        raiz = ctx.raiz()
        h0 = raiz.h
        frontera: list = []
        contador = 0
        heapq.heappush(frontera, (*self._clave(raiz, contador), raiz))
        mejor = raiz
        cerrados: set = set()
        max_front = 1
        terminado = "agotado"
        hoja = None
        while frontera:
            motivo = pres.agotado()
            if motivo is not None:
                terminado = motivo
                break
            nodo = heapq.heappop(frontera)[-1]
            if ctx.es_hoja(nodo):
                hoja = nodo
                terminado = "meta"
                break
            if self.detectar_repetidos:
                clave = ctx.clave(nodo)
                if clave in cerrados:
                    traza.registrar("podar", profundidad=nodo.prof,
                                    nota="estado repetido")
                    continue
                cerrados.add(clave)
            estado = ctx.estado_de(nodo)
            pres.nodos_expandidos += 1
            traza.registrar("expandir", asignacion=foto(estado.asignacion),
                            F=self._f(nodo), profundidad=nodo.prof,
                            tam_frontera=len(frontera))
            hijos = sucesores(ctx, nodo, estado)
            pres.nodos_generados += len(hijos)
            for hijo in hijos:
                contador += 1
                heapq.heappush(frontera, (*self._clave(hijo, contador), hijo))
                mejor = mejor_visto(mejor, hijo)
            max_front = max(max_front, len(frontera))
            if pres.nodos_expandidos % CADA_FRONTERA == 0:
                traza.registrar("frontera", tam_frontera=len(frontera))
        final = hoja if hoja is not None else mejor
        estado_final = ctx.estado_de(final)
        extra = {"saltados": final.n_saltados, "g": final.g,
                 "h_inicial": h0, "max_frontera": max_front}
        res = resultado_desde(self.nombre, estado_final, pres, terminado,
                              traza, self.parametros, extra)
        if hoja is not None and res.exito:
            traza.registrar("solucion", F=res.F, v=0)
        traza.registrar("fin", nota=terminado, F=res.F, v=res.v)
        return res


class AEstrella(_Informada):
    """A*: f = g + peso_h·h. Óptima respecto de g con peso_h = 1 (h admisible).

    Desempate determinista: (f, -profundidad, orden de inserción); preferir
    nodos profundos entre f iguales evita explorar a lo ancho las mesetas.
    """

    nombre = "a_estrella"

    def _f(self, nodo):
        return nodo.g + self.peso_h * nodo.h

    def _clave(self, nodo, contador):
        return (self._f(nodo), -nodo.prof, nodo.restr, contador)


class Avara(_Informada):
    """Búsqueda avara: f = h_avara = h + peso_distancia·(#no decididos).

    La avara NO necesita una heurística admisible: solo busca "parecer cerca
    de la meta". Por eso usa h_avara(n) = h_admisible(n) + peso_distancia ·
    (bloques por decidir), la "distancia a la meta". h_avara NO es admisible
    (el segundo término no acota el costo restante, que puede ser 0 aun con
    muchos bloques por decidir), y eso no importa: la avara no promete
    optimalidad, solo velocidad. Al preferir siempre el nodo con menos
    bloques por decidir se zambulle en profundidad (casi sin retroceder),
    mucho más rápido que A*. Termina en la primera hoja, que puede tener g
    mayor que el óptimo. A* sigue usando la h admisible. Desempate:
    (h_avara, -profundidad, restr, orden de inserción).

    Además se suma λ·#saltados: sin ese término "saltar" siempre parecería
    el hijo más cercano a la meta (quita el término del bloque de h y no
    paga nada) y la avara descartaría bloques sin necesidad.

    Parámetros: ``detectar_repetidos`` (poda de estados repetidos) y
    ``peso_distancia`` (peso de los bloques por decidir en h_avara). No tiene
    ``peso_h``: su f no usa la h admisible ponderada, así que aceptarlo
    sería engañoso.
    """

    nombre = "avara"

    def __init__(self, detectar_repetidos: bool = True,
                 peso_distancia: float = 1.0):
        super().__init__(peso_h=1.0, detectar_repetidos=detectar_repetidos)
        del self.parametros["peso_h"]
        self.parametros["peso_distancia"] = peso_distancia
        self.peso_distancia = peso_distancia
        self._total = 0
        self._lam = 0.0

    def _f(self, nodo):
        return (nodo.h + self.peso_distancia * (self._total - nodo.prof)
                + self._lam * nodo.n_saltados)

    def _clave(self, nodo, contador):
        return (self._f(nodo), -nodo.prof, nodo.restr, contador)
