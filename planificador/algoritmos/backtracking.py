"""Backtracking cronológico como CSP (propuesta, sección 4.1).

Formulación como problema de satisfacción de restricciones (CSP)
----------------------------------------------------------------
* **Variables**: los bloques sin ubicar U(X0) del estado inicial. Los bloques
  ya ubicados quedan fijos.
* **Dominio** de un bloque: posiciones (día, franja, salón) legales
  (``comun.dominio_unario``: salón libre, tipo, capacidad, disponibilidad A y
  ventana W) y, además, consistentes con lo ya ubicado
  (``comun.dominio_consistente``: no cruzan docente ni grupo).
* **Restricciones binarias**: dos bloques vecinos en el grafo de conflictos Γ
  (mismo docente o algún grupo común) no pueden traslaparse en el tiempo, y
  dos bloques no virtuales no pueden ocupar el mismo salón en una misma celda.
  Esta última restricción también liga a bloques que NO son vecinos en Γ.

Búsqueda
--------
Búsqueda en profundidad con retroceso: se elige una variable, se prueban sus
valores y se desciende; si la rama falla se deshace la asignación y se prueba
el siguiente valor. En el peor caso el árbol tiene O(d^n) nodos (d = tamaño
del dominio, n = número de variables), es decir, **crece exponencialmente**:
el problema de horarios es NP-completo y ningún truco cambia esa cota en el
peor caso. Las heurísticas siguientes solo reducen el árbol en la práctica:

* **MRV** (mínimos valores restantes, "fail-first"): se elige primero la
  variable con el dominio más pequeño, porque es la más probable de fallar;
  fallar pronto poda subárboles enormes. El desempate usa el **grado** en Γ
  (más vecinos primero): la variable que más restringe a las demás.
* **Forward checking** (comprobación hacia adelante): al ubicar m en p se
  eliminan de los dominios de las variables aún sin decidir los valores que
  esa asignación vuelve inconsistentes (traslape de tiempo con p para los
  vecinos de m en Γ; mismo salón y celdas comunes para cualquier bloque,
  vecino o no). Si algún dominio queda vacío, la rama no puede completarse y se
  retrocede de inmediato, sin descender. Los cambios se guardan en una pila
  (trail) y se revierten al deshacer: no se copian dominios por nodo.
* **Orden de valores** (por defecto ``lcv``). MRV elige la *variable* con
  criterio "fail-first" (la más difícil primero); el orden de valores debe ser
  el opuesto, "succeed-first": probar primero el valor que deja más libertad.

  - ``lcv`` (*least constraining value*): los valores de x se ordenan por la
    tupla (posiciones que el valor eliminaría de los dominios actuales de las
    variables pendientes, delta blando, índice original). Se cuentan los
    horarios (día, franja) distintos que perderían los vecinos de x en Γ
    (traslape temporal; igual que ``restr`` de la búsqueda Avara) y las
    posiciones de bloques no vecinos no virtuales (mismo salón y traslape),
    como haría el forward checking. Se agrupa por (día, franja) con sumas
    prefijas, sin comparar todos los pares de posiciones.
  - ``f_incremental``: por costo blando incremental creciente (horas extremas,
    huecos y carga), de modo que las primeras soluciones ya sean buenas.
  - ``natural``: el orden del dominio.

Saltar bloques (variable sin dominio)
-------------------------------------
Si un bloque no puede ubicarse, se puede dejar sin ubicar (cuesta 1 en v por
U(X)). Para que el modo ``primera`` devuelva v = 0 siempre que exista, la
búsqueda se hace en **dos fases**:

* Fase A (sin saltos): cota de saltos = 1, es decir, toda rama con un dominio
  vacío se poda. Es el backtracking CSP clásico y completo para v = 0.
* Fase B (solo si la fase A agota el árbol sin hallar solución y
  ``permitir_saltar``): el salto se intenta únicamente como **última opción**,
  tras agotar los valores del dominio de la variable, y se mantiene una cota de
  branch & bound: no se exploran ramas cuyos saltos (más las variables que ya
  tienen dominio vacío, que forzosamente se saltarán) igualen o superen los del
  mejor estado completo hallado. Así se devuelve el mínimo número de saltos.

Presupuesto por fases
---------------------
Si ``permitir_saltar``, la fase A solo puede gastar la fracción
``fraccion_fase_a`` (0 < f <= 1) de ``max_nodos`` y ``max_segundos``; si la
agota sin solución completa se pasa a la fase B con lo que quede del
presupuesto total (el conteo de nodos y tiempo no se reinicia, así que el
``Resultado`` respeta siempre los ``Limites`` originales). Sin saltos, la fase
A usa todo el presupuesto.

Modos
-----
* ``primera``: termina con la primera asignación completa sin saltos
  (``terminado_por = "meta"``). Si hace falta saltar, termina por agotamiento
  con el mínimo de saltos.
* ``optimizar``: branch & bound sobre F. Tras cada solución sigue buscando; se
  poda cuando λ·(saltos + vacíos) + w_ext·φ_extrema >= mejor F conocido. Solo
  se usan términos monótonos (nunca decrecen al decidir más bloques). Termina
  por agotamiento (el mejor F hallado es el óptimo) o por presupuesto.
  Supuesto: λ es mayor que el rango de f (λ automático = cota + 1), de modo
  que una solución completa sin saltos siempre supera a una con saltos; por
  eso la fase B solo se ejecuta si la fase A no halló ninguna solución.

Mejor estado y traza
--------------------
Siempre se conserva el mejor estado visto (menor F): los estados completos se
evalúan al completarse y los parciales solo cuando alcanzan un nuevo máximo de
bloques ubicados (para no evaluar F en cada nodo). La traza registra
``add``/``del`` en orden, de modo que aplicarlos desde el estado inicial
reconstruye el estado en cualquier paso. Antes de ``fin`` se registran los
``del``/``add`` necesarios para que el estado final de la traza coincida con
el estado devuelto (que puede diferir del estado actual de la búsqueda).

Profundidad de recursión: es a lo sumo el número de variables (+1); con 200
bloques basta el límite por defecto, pero se sube localmente de forma
automática si hiciera falta y se restaura al terminar.
"""

from __future__ import annotations

import sys
from typing import Optional

from planificador.core import costo
from planificador.core.acciones import aplicar_en_sitio
from planificador.core.conflictos import construir_conflictos
from planificador.core.estado import Estado
from planificador.core.modelo import Anadir, Eliminar, Instancia, Posicion

from .base import Limites, Presupuesto, Resultado, Solver, Traza
from .comun import (consistente, dominio_consistente, elegir_mrv,
                    resultado_desde)

MODOS = ("primera", "optimizar")
ORDENES = ("lcv", "f_incremental", "natural")
INFINITO = float("inf")


def _huecos(franjas) -> int:
    """Franjas vacías entre la primera y la última ocupada de un día."""
    if not franjas:
        return 0
    return max(franjas) - min(franjas) + 1 - len(franjas)


def _solapan(dia, franja, dur, q: Posicion, dur_q) -> bool:
    """True si dos bloques (mismo día, rangos de franjas) se traslapan."""
    return (q.dia == dia and q.franja < franja + dur
            and franja < q.franja + dur_q)


class _Busqueda:
    """Estado de una ejecución (se crea una por cada ``resolver``)."""

    def __init__(self, solver, instancia, estado, limites):
        self.s = solver
        self.inst = instancia
        self.estado = estado
        self.pres = Presupuesto(limites)
        self.traza = Traza(limites.max_eventos_traza)
        self.gamma = construir_conflictos(instancia)
        self.lam = costo.lam(instancia)
        self.w = instancia.pesos
        self.extrema = [fr.extrema for fr in instancia.franjas]
        self.inicial = dict(estado.asignacion)
        self.motivo: Optional[str] = None
        # Tope de la fase A: (nodos, segundos) absolutos o None.
        self.tope_fase: Optional[tuple] = None
        self.fase_agotada = False
        # Dominios de las variables pendientes (aún no decididas).
        self.dom = {m: dominio_consistente(estado, m)
                    for m in sorted(estado.sin_ubicar())}
        self.num_vars = len(self.dom)
        self.vacios = sum(1 for d in self.dom.values() if not d)
        self.trail: list = []
        self.cota_saltos = 1
        # Término monótono w_ext * φ_extrema del estado actual.
        self.ext = sum(self._extremas(m, p)
                       for m, p in estado.asignacion.items())
        self.mejor_F_comp = INFINITO     # solo estados completos
        self.mejor = None                # (F, asignacion) cualquier estado
        self.mejor_F = INFINITO
        self.max_ubicados = -1
        self.soluciones = 0
        self.prof_max = 0
        self._entidades: dict = {}
        self._candidato()                # el estado inicial es un candidato

    # ------------------------------------------------------------------
    # utilidades
    # ------------------------------------------------------------------
    def _extremas(self, bloque_id, pos) -> float:
        dur = self.inst.bloque[bloque_id].duracion
        n = sum(1 for h in range(pos.franja, pos.franja + dur)
                if self.extrema[h])
        return self.w.hora_extrema * n

    def _candidato(self):
        """Evalúa el estado actual y lo guarda si mejora el mejor visto."""
        est = self.estado
        v = costo.violaciones(est).total
        F = costo.f(est) + self.lam * v
        self.max_ubicados = max(self.max_ubicados, len(est.asignacion))
        if F < self.mejor_F:
            self.mejor_F = F
            self.mejor = dict(est.asignacion)
        return v, F

    def _delta(self, bloque_id, pos, cache) -> float:
        """Costo blando incremental aproximado de ubicar el bloque en pos.

        Considera horas extremas, huecos de docente y grupo y carga diaria.
        Ignora dispersión y cambio de sede (solo se usa para ordenar valores).
        """
        inst, w, est = self.inst, self.w, self.estado
        b = inst.bloque[bloque_id]
        ents = self._entidades.get(bloque_id)
        if ents is None:
            ents = []
            if b.docente_id is not None:
                ents.append(("d", b.docente_id,
                             inst.docente[b.docente_id].max_franjas_dia,
                             w.hueco_docente))
            for g in b.grupos:
                ents.append(("g", g, inst.grupo[g].max_franjas_dia,
                             w.hueco_grupo))
            self._entidades[bloque_id] = ents
        nuevas = range(pos.franja, pos.franja + b.duracion)
        total = self._extremas(bloque_id, pos)
        for tipo, eid, tope, w_hueco in ents:
            clave = (tipo, eid, pos.dia)
            ocup = cache.get(clave)
            if ocup is None:
                cuenta = (est.ocupacion_docente if tipo == "d"
                          else est.ocupacion_grupo)
                ocup = frozenset(h for h in range(inst.num_franjas)
                                 if cuenta(eid, (pos.dia, h)) > 0)
                cache[clave] = ocup
            despues = ocup.union(nuevas)
            total += w_hueco * (_huecos(despues) - _huecos(ocup))
            if tope is not None:
                total += w.carga_grupo * (max(0, len(despues) - tope)
                                          - max(0, len(ocup) - tope))
        return total

    def _restricciones(self, x, valores) -> list:
        """Posiciones que cada valor de x quitaría a los dominios pendientes.

        Cuenta lo que podaría ``_filtrar`` con una diferencia deliberada: de
        cada vecino en Γ se cuentan los horarios (día, franja) distintos que
        perdería, no sus posiciones (un horario con 5 salones cuenta 1), como
        hace ``restr`` en la búsqueda Avara; contarlas todas sesga la
        elección hacia horarios con pocos salones y atasca la búsqueda. Los
        bloques no vecinos sí se cuentan por posición (mismo salón). Se
        agrupa: para cada duración y día se acumulan los inicios en un
        arreglo con sumas prefijas, y cada valor consulta un rango.
        """
        inst = self.inst
        nf = inst.num_franjas
        dx = inst.bloque[x].duracion
        vecinos = self.gamma[x]
        bloque = inst.bloque
        tiempo: dict = {}     # (du, dia) -> inicios por franja (vecinos)
        salon: dict = {}      # (du, salon, dia) -> inicios por franja
        for u, dom_u in self.dom.items():
            if not dom_u:
                continue
            du = bloque[u].duracion
            if u in vecinos:
                destino, pref = tiempo, ()
            elif not bloque[u].virtual:
                destino, pref = salon, None
            else:
                continue
            vistos = set()
            for q in dom_u:
                if pref is not None:
                    # Vecinos en Γ: solo importa el horario, no el salón
                    # (cada (día, franja) cuenta una vez por vecino).
                    if (q.dia, q.franja) in vistos:
                        continue
                    vistos.add((q.dia, q.franja))
                if pref is None:
                    if inst.salon[q.salon].virtual:
                        continue
                    clave = (du, q.salon, q.dia)
                else:
                    clave = (du, q.dia)
                arr = destino.get(clave)
                if arr is None:
                    arr = destino[clave] = [0] * (nf + 1)
                arr[q.franja + 1] += 1
        for destino in (tiempo, salon):
            for arr in destino.values():
                for i in range(1, nf + 1):
                    arr[i] += arr[i - 1]
        res = []
        memo: dict = {}
        for p in valores:
            fisico = not inst.salon[p.salon].virtual
            clave_p = (p.dia, p.franja, p.salon if fisico else None)
            tot = memo.get(clave_p)
            if tot is None:
                # q se traslapa con p si q.franja en (p.franja - du, fin_p).
                tot = 0
                hi = min(p.franja + dx, nf)
                for (du, dia), arr in tiempo.items():
                    if dia == p.dia:
                        lo = max(p.franja - du + 1, 0)
                        tot += arr[hi] - arr[lo]
                if fisico:
                    for (du, sal, dia), arr in salon.items():
                        if dia == p.dia and sal == p.salon:
                            lo = max(p.franja - du + 1, 0)
                            tot += arr[hi] - arr[lo]
                memo[clave_p] = tot
            res.append(tot)
        return res

    def _ordenar(self, bloque_id, valores) -> list:
        orden = self.s.orden_valores
        if orden == "natural" or len(valores) < 2:
            return list(valores)
        cache: dict = {}
        if orden == "lcv":
            restr = self._restricciones(bloque_id, valores)
            claves = [(restr[i], self._delta(bloque_id, p, cache), i)
                      for i, p in enumerate(valores)]
        else:
            claves = [(self._delta(bloque_id, p, cache), i)
                      for i, p in enumerate(valores)]
        claves.sort()
        return [valores[c[-1]] for c in claves]

    # ------------------------------------------------------------------
    # forward checking
    # ------------------------------------------------------------------
    def _filtrar(self, x, p, saltos) -> bool:
        """Poda los dominios pendientes tras ubicar x en p.

        Devuelve False si la rama ya no puede mejorar la cota de saltos.
        Todo cambio queda en ``self.trail`` para poder revertirse.
        """
        inst = self.inst
        dx = inst.bloque[x].duracion
        vecinos = self.gamma[x]
        salon_fisico = not inst.salon[p.salon].virtual
        bloque = inst.bloque
        for u in list(self.dom):
            dom_u = self.dom[u]
            if not dom_u:
                continue
            du = bloque[u].duracion
            if u in vecinos:
                nuevo = [q for q in dom_u
                         if not _solapan(p.dia, p.franja, dx, q, du)]
            elif salon_fisico and not bloque[u].virtual:
                nuevo = [q for q in dom_u
                         if not (q.salon == p.salon
                                 and _solapan(p.dia, p.franja, dx, q, du))]
            else:
                continue
            if len(nuevo) == len(dom_u):
                continue
            self.trail.append((u, dom_u))
            self.dom[u] = nuevo
            if not nuevo:
                self.vacios += 1
                self.traza.registrar("podar", bloque=u, nota="dominio vacio")
                if saltos + self.vacios >= self.cota_saltos:
                    return False
        return True

    def _revertir(self, marca) -> None:
        while len(self.trail) > marca:
            u, viejo = self.trail.pop()
            if not self.dom[u] and viejo:
                self.vacios -= 1
            self.dom[u] = viejo

    # ------------------------------------------------------------------
    # búsqueda
    # ------------------------------------------------------------------
    def _podar_por_cota(self, saltos) -> bool:
        s = saltos + self.vacios
        if s >= self.cota_saltos:
            return True
        if (self.s.modo == "optimizar" and self.mejor_F_comp < INFINITO
                and self.lam * s + self.ext >= self.mejor_F_comp):
            return True
        return False

    def _completo(self, saltos) -> None:
        """Se decidieron todas las variables: registra la solución."""
        v, F = self._candidato()
        self.soluciones += 1
        if F < self.mejor_F_comp:
            self.mejor_F_comp = F
            self.traza.registrar("mejora", F=F, v=v,
                                 f=F - self.lam * v)
            if v == 0:
                self.traza.registrar("solucion", F=F, v=v)
        if 0 < saltos < self.cota_saltos:
            self.cota_saltos = saltos
        if self.s.modo == "primera" and saltos == 0:
            self.motivo = "meta" if v == 0 else "agotado"

    def _fase_agotada(self) -> bool:
        """True si se agotó el tope propio de la fase A (no el total).

        El tope solo existe para dejarle presupuesto a la fase B. Si ya hay
        una solución completa, la fase B no se ejecutará, así que la fase A
        conserva todo el presupuesto (sin esto, ``optimizar`` se cortaba y
        reportaba "agotado" como si hubiera probado optimalidad).
        """
        if self.tope_fase is None or self.mejor_F_comp < INFINITO:
            return False
        nodos, seg = self.tope_fase
        if ((nodos is not None and self.pres.nodos_expandidos >= nodos)
                or (seg is not None and self.pres.transcurrido() >= seg)):
            self.fase_agotada = True
            return True
        return False

    def reiniciar_fase(self) -> None:
        """Deshace lo ubicado por la fase A y recalcula los dominios."""
        est = self.estado
        for m in sorted(est.asignacion):
            if m not in self.inicial:
                pos = est.asignacion[m]
                aplicar_en_sitio(est, Eliminar(m))
                self.traza.registrar("del", bloque=m, posicion=pos)
        self.dom = {m: dominio_consistente(est, m)
                    for m in sorted(est.sin_ubicar())}
        self.vacios = sum(1 for d in self.dom.values() if not d)
        self.trail = []
        self.ext = sum(self._extremas(m, p)
                       for m, p in est.asignacion.items())
        self.tope_fase = None
        self.fase_agotada = False

    def buscar(self, saltos, prof) -> bool:
        """Devuelve True si hay que detener toda la búsqueda."""
        if prof > self.prof_max:
            self.prof_max = prof
        if not self.dom:
            self._completo(saltos)
            return self.motivo is not None
        if self._podar_por_cota(saltos):
            self.traza.registrar("podar", nota="cota", profundidad=prof)
            return False
        x = (elegir_mrv(self.dom, self.gamma) if self.s.mrv
             else min(self.dom))
        valores = self.dom.pop(x)
        vacio = not valores
        if vacio:
            self.vacios -= 1
        self.pres.nodos_generados += len(valores)
        self.traza.registrar("expandir", bloque=x, profundidad=prof,
                             tam_frontera=len(valores))
        fc = self.s.forward_checking
        for p in self._ordenar(x, valores):
            motivo = self.pres.agotado()
            if motivo:
                self.motivo = motivo
                return True
            if self._fase_agotada():
                return True
            self.pres.nodos_expandidos += 1
            if not fc and not consistente(self.estado, x, p):
                continue
            try:
                inversa = aplicar_en_sitio(self.estado, Anadir(x, p))
            except ValueError:
                continue
            self.traza.registrar("add", bloque=x, posicion=p,
                                 profundidad=prof)
            self.ext += self._extremas(x, p)
            marca = len(self.trail)
            if len(self.estado.asignacion) > self.max_ubicados:
                self._candidato()
            if not fc or self._filtrar(x, p, saltos):
                if self.buscar(saltos, prof + 1):
                    return True
            self._revertir(marca)
            self.ext -= self._extremas(x, p)
            aplicar_en_sitio(self.estado, inversa)
            self.traza.registrar("del", bloque=x, posicion=p,
                                 profundidad=prof)
        # Última opción: dejar x sin ubicar (solo en la fase B).
        if self.cota_saltos > 1 and self.s.permitir_saltar:
            if self.buscar(saltos + 1, prof + 1):
                return True
        self.dom[x] = valores
        if vacio:
            self.vacios += 1
        self.traza.registrar("retroceder", bloque=x, profundidad=prof)
        return False

    def sincronizar_traza(self) -> None:
        """Deja la traza en el mejor estado (add/del hasta igualarlo)."""
        actual = dict(self.estado.asignacion)
        mejor = self.mejor
        for m in sorted(actual):
            if mejor.get(m) != actual[m]:
                self.traza.registrar("del", bloque=m, posicion=actual[m])
        for m in sorted(mejor):
            if actual.get(m) != mejor[m]:
                self.traza.registrar("add", bloque=m, posicion=mejor[m])


class Backtracking(Solver):
    """Backtracking CSP con MRV, forward checking y branch & bound opcional."""

    nombre = "backtracking"

    def __init__(self, modo: str = "primera", mrv: bool = True,
                 forward_checking: bool = True, permitir_saltar: bool = True,
                 orden_valores: str = "lcv",
                 fraccion_fase_a: float = 0.7):
        if modo not in MODOS:
            raise ValueError(f"modo inválido: {modo}")
        if orden_valores not in ORDENES:
            raise ValueError(f"orden_valores inválido: {orden_valores}")
        if not 0 < fraccion_fase_a <= 1:
            raise ValueError(
                f"fraccion_fase_a debe estar en (0, 1]: {fraccion_fase_a}")
        super().__init__(modo=modo, mrv=mrv,
                         forward_checking=forward_checking,
                         permitir_saltar=permitir_saltar,
                         orden_valores=orden_valores,
                         fraccion_fase_a=fraccion_fase_a)
        self.modo = modo
        self.mrv = mrv
        self.forward_checking = forward_checking
        self.permitir_saltar = permitir_saltar
        self.orden_valores = orden_valores
        self.fraccion_fase_a = fraccion_fase_a

    def resolver(self, instancia: Instancia, estado_inicial=None,
                 limites: Limites = Limites()) -> Resultado:
        estado = (estado_inicial.copiar() if estado_inicial is not None
                  else Estado(instancia))
        b = _Busqueda(self, instancia, estado, limites)
        limite_previo = sys.getrecursionlimit()
        necesario = b.num_vars + 500
        if necesario > limite_previo:
            sys.setrecursionlimit(necesario)
        try:
            # Fase A: sin saltos (cota de saltos = 1). Con saltos
            # permitidos solo gasta una fracción del presupuesto.
            if self.permitir_saltar:
                f = self.fraccion_fase_a
                b.tope_fase = (
                    None if limites.max_nodos is None
                    else limites.max_nodos * f,
                    None if limites.max_segundos is None
                    else limites.max_segundos * f)
            b.buscar(0, 0)
            # Fase B: permitir saltos, solo si A no halló nada completo.
            if (b.motivo is None and self.permitir_saltar
                    and b.mejor_F_comp == INFINITO):
                if b.fase_agotada:
                    b.reiniciar_fase()
                b.tope_fase = None
                b.cota_saltos = INFINITO
                b.buscar(0, 0)
            if b.motivo is None:
                b.motivo = "agotado"
        finally:
            sys.setrecursionlimit(limite_previo)
        b.sincronizar_traza()
        b.traza.registrar("fin", nota=b.motivo)
        final = Estado(instancia, b.mejor)
        saltados = b.num_vars - sum(
            1 for m in b.mejor if m not in b.inicial)
        return resultado_desde(
            self.nombre, final, b.pres, b.motivo, b.traza,
            parametros=dict(self.parametros),
            extra={"saltados": saltados,
                   "soluciones_encontradas": b.soluciones,
                   "profundidad_max": b.prof_max})
