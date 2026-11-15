"""Tests del solver Backtracking (CSP con MRV, forward checking y B&B)."""

import pytest

from planificador.algoritmos.backtracking import Backtracking
from planificador.algoritmos.base import Limites
from planificador.core import costo
from planificador.core.acciones import aplicar_en_sitio
from planificador.core.conflictos import construir_conflictos
from planificador.core.estado import Estado
from planificador.core.modelo import Anadir, Eliminar, Posicion, celdas_de
from planificador.core.validador import validar
from planificador.io_datos.sintetico import generar_instancia
from tests.fixtures.instancias_mini import (
    mini_factible, mini_infactible, mini_reparacion,
    mini_sin_disponibilidad, mini_virtual)

HOLGADO = Limites(max_nodos=None, max_segundos=60.0)


def _valido(instancia, resultado):
    return validar(instancia, resultado.asignacion).violaciones.total


# ----------------------------------------------------------------------
# Fixtures mini
# ----------------------------------------------------------------------

@pytest.mark.parametrize("fabrica", [mini_factible, mini_reparacion,
                                     mini_virtual])
def test_mini_factibles(fabrica):
    fx = fabrica()
    r = Backtracking().resolver(fx["instancia"], limites=HOLGADO)
    assert r.exito and r.terminado_por == "meta"
    assert _valido(fx["instancia"], r) == 0
    assert r.extra["saltados"] == 0
    assert r.algoritmo == "backtracking"


def test_mini_infactible_saltando():
    fx = mini_infactible()
    r = Backtracking(permitir_saltar=True).resolver(
        fx["instancia"], limites=HOLGADO)
    assert r.v == fx["v_minimo"] == 1
    assert r.extra["saltados"] == 1
    assert _valido(fx["instancia"], r) == 1
    assert r.terminado_por == "agotado"


def test_mini_infactible_sin_saltar():
    fx = mini_infactible()
    r = Backtracking(permitir_saltar=False).resolver(
        fx["instancia"], limites=HOLGADO)
    assert not r.exito
    assert r.terminado_por == "agotado"
    assert isinstance(r.asignacion, dict)
    # Devuelve el mejor parcial: un bloque ubicado de los dos.
    assert len(r.asignacion) == 1


def test_mini_sin_disponibilidad():
    """dominio_unario excluye posiciones que violan A: el bloque queda
    saltado, v = 1 (saltar cuesta 1; ubicarlo en no disponible costaría 2)."""
    fx = mini_sin_disponibilidad()
    r = Backtracking().resolver(fx["instancia"], limites=HOLGADO)
    assert r.v == 1
    assert r.asignacion == {}
    assert r.extra["saltados"] == 1
    assert _valido(fx["instancia"], r) == 1
    sin_saltar = Backtracking(permitir_saltar=False).resolver(
        fx["instancia"], limites=HOLGADO)
    assert sin_saltar.v == 1 and sin_saltar.terminado_por == "agotado"


# ----------------------------------------------------------------------
# Estado inicial
# ----------------------------------------------------------------------

def test_estado_inicial_fijos_y_sin_mutar():
    fx = mini_factible()
    inst = fx["instancia"]
    fijo = Posicion(1, 0, "S1")
    inicial = Estado(inst, {"B2": fijo})
    clave = inicial.clave()
    r = Backtracking().resolver(inst, inicial, HOLGADO)
    assert r.asignacion["B2"] == fijo
    assert r.exito and _valido(inst, r) == 0
    assert inicial.clave() == clave
    assert set(inicial.asignacion) == {"B2"}


def test_estado_inicial_completo_es_meta_inmediata():
    fx = mini_factible()
    inicial = Estado(fx["instancia"], fx["solucion"])
    r = Backtracking().resolver(fx["instancia"], inicial, HOLGADO)
    assert r.exito and r.asignacion == fx["solucion"]
    assert r.terminado_por == "meta"


# ----------------------------------------------------------------------
# Sintéticas
# ----------------------------------------------------------------------

@pytest.mark.parametrize("n", [20, 50, 100])
def test_sinteticas_primera(n, capsys):
    inst, _ = generar_instancia(n, 7)
    r = Backtracking().resolver(inst, limites=Limites(max_segundos=20))
    with capsys.disabled():
        print(f"\n[backtracking primera] n={n} t={r.tiempo_s:.3f}s "
              f"nodos={r.nodos_expandidos} v={r.v}")
    assert r.exito and r.terminado_por == "meta"
    assert _valido(inst, r) == 0
    assert len(r.asignacion) == n


def test_sintetica_infactible_perturbada_devuelve_resultado():
    inst, _ = generar_instancia(20, 3, garantizar_factible=False,
                                prob_disponible=0.1)
    r = Backtracking().resolver(inst, limites=Limites(max_segundos=10))
    assert r.v == _valido(inst, r)
    assert r.terminado_por in ("agotado", "limite_nodos", "limite_tiempo",
                               "meta")


# ----------------------------------------------------------------------
# Optimizar vs. fuerza bruta
# ----------------------------------------------------------------------

def _fuerza_bruta(inst):
    """Mínimo F entre todas las asignaciones completas con v = 0.

    Enumeración independiente: dominio por bloque comprobado con el validador
    (solo ese bloque ubicado) y retroceso con verificación por pares; el F de
    cada solución completa lo calcula ``core.costo`` sobre un Estado.
    """
    bloques = [b.id for b in inst.bloques]
    gamma = construir_conflictos(inst)
    dominios = {}
    for m in bloques:
        dominios[m] = []
        for d in range(inst.num_dias):
            for h in range(inst.num_franjas):
                for s in inst.salones:
                    pos = Posicion(d, h, s.id)
                    rep = validar(inst, {m: pos}).violaciones
                    if (rep.disponibilidad == rep.ventana == rep.conflicto
                            == rep.salon == 0):
                        dominios[m].append(pos)
    mejor = [float("inf"), 0]
    asignacion = {}

    def compatible(m, pos):
        cm = set(celdas_de(pos, inst.bloque[m].duracion))
        for o, po in asignacion.items():
            co = set(celdas_de(po, inst.bloque[o].duracion))
            if cm & co and (o in gamma[m] or (
                    pos.salon == po.salon
                    and not inst.salon[pos.salon].virtual)):
                return False
        return True

    def rec(i):
        if i == len(bloques):
            mejor[1] += 1
            F = costo.F(Estado(inst, dict(asignacion)))
            mejor[0] = min(mejor[0], F)
            return
        m = bloques[i]
        for pos in dominios[m]:
            if compatible(m, pos):
                asignacion[m] = pos
                rec(i + 1)
                del asignacion[m]

    rec(0)
    return mejor


@pytest.mark.parametrize("semilla", [1, 3])
def test_optimizar_es_optimo(semilla):
    inst, _ = generar_instancia(8, semilla, num_dias=2, num_franjas=4)
    primera = Backtracking(modo="primera").resolver(inst, limites=HOLGADO)
    opt = Backtracking(modo="optimizar").resolver(inst, limites=HOLGADO)
    assert opt.terminado_por == "agotado"
    assert opt.exito and _valido(inst, opt) == 0
    assert opt.F <= primera.F + 1e-9
    optimo, cuantas = _fuerza_bruta(inst)
    assert cuantas >= 1
    assert opt.F == pytest.approx(optimo)
    assert validar(inst, opt.asignacion).F == pytest.approx(optimo)


def test_optimizar_registra_mejoras():
    inst, _ = generar_instancia(8, 3, num_dias=2, num_franjas=4)
    r = Backtracking(modo="optimizar").resolver(inst, limites=HOLGADO)
    mejoras = [e.F for e in r.traza.eventos if e.tipo == "mejora"]
    assert mejoras and mejoras == sorted(mejoras, reverse=True)
    assert mejoras[-1] == pytest.approx(r.F)


def test_orden_natural_tambien_optimo():
    inst, _ = generar_instancia(8, 3, num_dias=2, num_franjas=4)
    a = Backtracking(modo="optimizar").resolver(inst, limites=HOLGADO)
    b = Backtracking(modo="optimizar", orden_valores="natural").resolver(
        inst, limites=HOLGADO)
    assert a.F == pytest.approx(b.F)


# ----------------------------------------------------------------------
# MRV y forward checking
# ----------------------------------------------------------------------

@pytest.mark.parametrize("mrv,fc", [(True, True), (True, False),
                                    (False, True), (False, False)])
def test_variantes_hallan_solucion(mrv, fc):
    inst, _ = generar_instancia(8, 1, num_dias=2, num_franjas=4)
    r = Backtracking(mrv=mrv, forward_checking=fc).resolver(
        inst, limites=HOLGADO)
    assert r.exito and _valido(inst, r) == 0


def test_mrv_fc_menos_nodos_que_sin_heuristicas():
    inst, _ = generar_instancia(20, 7)
    con = Backtracking().resolver(inst, limites=HOLGADO)
    sin = Backtracking(mrv=False, forward_checking=False).resolver(
        inst, limites=HOLGADO)
    assert con.exito and sin.exito
    assert con.nodos_expandidos <= sin.nodos_expandidos


# ----------------------------------------------------------------------
# Presupuesto, traza, determinismo
# ----------------------------------------------------------------------

def test_limite_nodos():
    inst, _ = generar_instancia(20, 7)
    r = Backtracking().resolver(inst, limites=Limites(max_nodos=5))
    assert r.terminado_por == "limite_nodos"
    assert r.nodos_expandidos <= 5
    assert _valido(inst, r) == r.v
    assert not r.exito
    assert r.traza.eventos[-1].tipo == "fin"
    assert r.traza.eventos[-1].nota == "limite_nodos"


def test_limite_tiempo():
    inst, _ = generar_instancia(100, 7)
    r = Backtracking().resolver(
        inst, limites=Limites(max_nodos=None, max_segundos=0.0))
    assert r.terminado_por == "limite_tiempo"


def _reconstruir(inst, inicial, traza):
    est = inicial.copiar()
    for e in traza.eventos:
        if e.tipo == "add":
            aplicar_en_sitio(est, Anadir(e.bloque, e.posicion))
        elif e.tipo == "del":
            aplicar_en_sitio(est, Eliminar(e.bloque))
    return est


@pytest.mark.parametrize("modo", ["primera", "optimizar"])
def test_traza_reconstruye_estado_final(modo):
    inst, _ = generar_instancia(8, 3, num_dias=2, num_franjas=4)
    inicial = Estado(inst)
    lim = Limites(max_nodos=None, max_segundos=60.0,
                  max_eventos_traza=10_000_000)
    r = Backtracking(modo=modo).resolver(inst, inicial, lim)
    assert not r.traza.truncada
    assert dict(_reconstruir(inst, inicial, r.traza).asignacion) \
        == r.asignacion
    tipos = {e.tipo for e in r.traza.eventos}
    assert {"expandir", "add", "fin"} <= tipos
    assert r.traza.eventos[-1].tipo == "fin"


def test_traza_reconstruye_con_saltos_y_limite():
    fx = mini_infactible()
    inicial = Estado(fx["instancia"])
    r = Backtracking().resolver(fx["instancia"], inicial, HOLGADO)
    assert dict(_reconstruir(fx["instancia"], inicial, r.traza).asignacion) \
        == r.asignacion
    inst, _ = generar_instancia(20, 7)
    ini = Estado(inst)
    r = Backtracking().resolver(inst, ini, Limites(max_nodos=5))
    assert dict(_reconstruir(inst, ini, r.traza).asignacion) == r.asignacion


def test_traza_truncada_no_revienta():
    inst, _ = generar_instancia(20, 7)
    r = Backtracking().resolver(
        inst, limites=Limites(max_eventos_traza=10, max_segundos=20))
    assert r.traza.truncada and r.exito
    assert r.traza.eventos[-1].tipo == "fin"


def test_determinismo():
    inst, _ = generar_instancia(50, 7)
    a = Backtracking().resolver(inst, limites=HOLGADO)
    b = Backtracking().resolver(inst, limites=HOLGADO)
    assert a.asignacion == b.asignacion
    assert a.nodos_expandidos == b.nodos_expandidos


def test_parametros_y_extra():
    r = Backtracking(modo="optimizar", mrv=False).resolver(
        mini_factible()["instancia"], limites=HOLGADO)
    assert r.parametros["modo"] == "optimizar"
    assert r.parametros["mrv"] is False
    assert set(r.extra) == {"saltados", "soluciones_encontradas",
                            "profundidad_max"}
    with pytest.raises(ValueError):
        Backtracking(modo="otro")
    with pytest.raises(ValueError):
        Backtracking(orden_valores="otro")
