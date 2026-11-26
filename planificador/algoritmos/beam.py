"""Búsqueda en haz (beam search): A* por niveles con memoria acotada.

Teoría
------
Beam search recorre el mismo árbol de decisiones que A* (ver
``informada.py``: nodo, costo de camino g, heurística h y sucesores) pero
nivel por nivel y conservando solo los ``ancho`` (k) mejores nodos de cada
nivel según f = g + h. Equivale a un A* con memoria acotada a k nodos por
nivel: se *poda de forma permanente* todo lo demás.

* Memoria O(k·profundidad) y tiempo O(k·b·profundidad) (b = factor de
  ramificación), frente a la frontera exponencial de A*.
* **Incompleto y no óptimo en general**: si el camino óptimo pasa por un nodo
  con f peor que k otros en algún nivel, se pierde para siempre. Con
  ``ancho -> infinito`` recupera la búsqueda exhaustiva por niveles (que con
  h admisible y f = g + h conserva el óptimo). Aquí, gracias a la opción
  "saltar" (siempre disponible), el haz nunca se vacía, así que siempre se
  llega a hojas: es completo en el sentido de "devuelve algún horario".
* Con ``ancho = 1`` es un avance voraz que escoge en cada nivel el hijo de
  menor g + h. NO coincide con la búsqueda avara (f = h, que puede
  retroceder y compara nodos de distinta profundidad); coinciden solo cuando
  el desempate lo permite.

Todos los nodos de un nivel tienen la misma profundidad, así que el haz
final contiene solo hojas; se devuelve la de menor g (y luego menor F
completo, que sí incluye huecos, dispersión y sede).

Trazas: ``expandir`` por cada nodo del haz (``asignacion=foto(...)``, F =
g + h), ``frontera`` por nivel (``tam_frontera`` = tamaño del haz), ``podar``
con el número de candidatos descartados en el nivel, ``solucion`` y ``fin``.
"""

from __future__ import annotations

from planificador.core import costo

from .base import Limites, Presupuesto, Solver, Traza, foto
from .comun import resultado_desde
from .informada import Contexto, mejor_visto, sucesores


class BeamSearch(Solver):
    """Beam search de ancho ``ancho`` sobre el árbol de A*."""

    nombre = "beam"

    def __init__(self, ancho: int = 10):
        if ancho < 1:
            raise ValueError("El ancho del haz debe ser >= 1")
        super().__init__(ancho=ancho)
        self.ancho = ancho

    def resolver(self, instancia, estado_inicial=None,
                 limites: Limites = Limites()):
        pres = Presupuesto(limites)
        traza = Traza(limites.max_eventos_traza)
        ctx = Contexto(instancia, estado_inicial)
        raiz = ctx.raiz()
        haz = [raiz]
        max_haz = len(haz)
        max_candidatos = 0
        max_estructura = len(haz)
        mejor = raiz
        niveles = 0
        terminado = "meta"
        while haz and not ctx.es_hoja(haz[0]):
            candidatos = []
            interrumpido = False
            for nodo in haz:
                motivo = pres.agotado()
                if motivo is not None:
                    terminado = motivo
                    interrumpido = True
                    break
                estado = ctx.estado_de(nodo)
                pres.nodos_expandidos += 1
                traza.registrar("expandir",
                                asignacion=foto(estado.asignacion),
                                F=nodo.g + nodo.h, profundidad=nodo.prof,
                                tam_frontera=len(haz))
                hijos = sucesores(ctx, nodo, estado)
                pres.nodos_generados += len(hijos)
                for hijo in hijos:
                    candidatos.append(hijo)
                max_candidatos = max(max_candidatos, len(candidatos))
                max_estructura = max(
                    max_estructura, len(haz) + len(candidatos)
                )
                mejor = mejor_visto(mejor, hijo)
            if interrumpido:
                break
            ordenados = sorted(
                enumerate(candidatos),
                key=lambda ic: (ic[1].g + ic[1].h, ic[1].g,
                                ic[1].restr, ic[0]))
            haz, vistos = [], set()
            for _, nodo in ordenados:
                if len(haz) >= self.ancho:
                    break
                clave = ctx.clave(nodo)
                if clave in vistos:
                    continue
                vistos.add(clave)
                haz.append(nodo)
            niveles += 1
            max_haz = max(max_haz, len(haz))
            max_estructura = max(max_estructura, len(haz))
            descartados = len(candidatos) - len(haz)
            traza.registrar("frontera", tam_frontera=len(haz),
                            profundidad=niveles)
            if descartados:
                traza.registrar("podar", profundidad=niveles,
                                nota=f"{descartados} candidatos descartados")
        hoja = None
        if terminado == "meta" and haz:
            hoja = self._mejor_hoja(ctx, haz)
        final = hoja if hoja is not None else mejor
        estado_final = ctx.estado_de(final)
        extra = {"saltados": final.n_saltados, "niveles": niveles,
                 "ancho": self.ancho, "max_haz": max_haz,
                 "max_candidatos": max_candidatos, 
                 "max_estructura": max_estructura
                 }
        res = resultado_desde(self.nombre, estado_final, pres, terminado,
                              traza, self.parametros, extra)
        if hoja is not None and res.exito:
            traza.registrar("solucion", F=res.F, v=0)
        traza.registrar("fin", nota=terminado, F=res.F, v=res.v)
        return res

    @staticmethod
    def _mejor_hoja(ctx, haz):
        """Hoja de menor g; desempate por F completo del core."""
        return min(haz, key=lambda n: (
            n.g, costo.F(ctx.estado_de(n))))
