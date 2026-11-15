"""Pruebas de la interfaz: módulos puros y humo con ``AppTest``."""

import random

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from planificador.algoritmos.reproduccion import cuadros_de_resultado
from planificador.app import edicion, ejecucion, graficas, vistas
from planificador.core.modelo import Posicion
from planificador.core.validador import validar
from planificador.io_datos.sintetico import generar_instancia
from tests.fixtures.instancias_mini import mini_factible, mini_reparacion

TIMEOUT = 90


@pytest.fixture(scope="module")
def sintetica():
    return generar_instancia(10, 3, num_dias=4, num_franjas=6)


def _asignacion_aleatoria(inst, semilla, k=None):
    """Posiciones al azar, sin respetar legalidad (para marcar violaciones)."""
    rng = random.Random(semilla)
    salones = [s.id for s in inst.salones]
    bloques = inst.bloques[:k] if k else inst.bloques
    asig = {}
    for b in bloques:
        h = rng.randrange(0, inst.num_franjas - b.duracion + 1)
        asig[b.id] = Posicion(rng.randrange(inst.num_dias), h,
                              rng.choice(salones))
    return asig


# --------------------------------------------------------------------------
# vistas
# --------------------------------------------------------------------------

def test_grilla_cuenta_celdas_de_cada_entidad(sintetica):
    inst, sol = sintetica
    esperado = {}
    for bid, pos in sol.items():
        b = inst.bloque[bid]
        esperado[pos.salon] = esperado.get(pos.salon, 0) + b.duracion
    for salon in inst.salones:
        g = vistas.construir_grilla(inst, sol, "Salón", salon.id)
        assert g.num_bloques_dibujados == esperado.get(salon.id, 0)
        assert len(g.filas) == inst.num_franjas
        assert len(g.dias) == inst.num_dias


def test_grilla_vistas_docente_y_grupo(sintetica):
    inst, sol = sintetica
    for d in inst.docentes:
        esp = sum(inst.bloque[b].duracion for b in sol
                  if inst.bloque[b].docente_id == d.id)
        g = vistas.construir_grilla(inst, sol, "Docente", d.id)
        assert g.num_bloques_dibujados == esp
    for gr in inst.grupos:
        esp = sum(inst.bloque[b].duracion for b in sol
                  if gr.id in inst.bloque[b].grupos)
        g = vistas.construir_grilla(inst, sol, "Grupo", gr.id)
        assert g.num_bloques_dibujados == esp


def test_grilla_resaltado_y_semana(sintetica):
    inst, sol = sintetica
    bid = sorted(sol)[0]
    pos = sol[bid]
    g = vistas.construir_grilla(inst, sol, "Salón", pos.salon,
                                resaltado=bid, dias=[pos.dia])
    assert any(c.resaltado for v in g.celdas.values() for c in v)
    assert g.dias == [pos.dia]
    html = vistas.grilla_a_html(g)
    assert html.startswith("<table") and bid in html


def test_marcas_coinciden_con_validador(sintetica):
    inst, _ = sintetica
    for semilla in range(5):
        asig = _asignacion_aleatoria(inst, semilla, k=8)
        resumen = vistas.resumen_marcas(
            vistas.violaciones_por_celda(inst, asig))
        viol = validar(inst, asig).violaciones
        assert resumen["disponibilidad"] == viol.disponibilidad
        assert resumen["ventana"] == viol.ventana
        assert resumen["conflicto"] == viol.conflicto


def test_solucion_oculta_no_tiene_marcas(sintetica):
    inst, sol = sintetica
    assert vistas.violaciones_por_celda(inst, sol) == {}


def test_celda_en_conflicto_se_marca_roja():
    inst = mini_factible()["instancia"]
    # B1 y B2 comparten docente o grupo: se ponen en la misma celda
    asig = {"B1": Posicion(1, 0, "S1"), "B2": Posicion(1, 0, "S2")}
    marcas = vistas.violaciones_por_celda(inst, asig)
    resumen = vistas.resumen_marcas(marcas)
    assert resumen["conflicto"] == validar(inst, asig).violaciones.conflicto
    if resumen["conflicto"]:
        g = vistas.construir_grilla(inst, asig, "Salón", "S1")
        assert any(c.malo for v in g.celdas.values() for c in v)
        assert "#c0152b" in vistas.grilla_a_html(g)


def test_movidos():
    a = {"x": Posicion(0, 0, "S"), "y": Posicion(1, 0, "S")}
    b = {"x": Posicion(0, 0, "S"), "y": Posicion(2, 0, "S")}
    assert vistas.bloques_movidos(a, b) == {"y"}
    assert vistas.bloques_movidos(a, {"x": a["x"]}) == {"y"}


def test_etiquetas_y_semanas(sintetica):
    inst, _ = sintetica
    assert vistas.hhmm(425) == "07:05"
    assert "07:00-08:00" in vistas.etiqueta_franja(inst, 0)
    assert vistas.semanas(inst) == [0]
    assert vistas.dias_de_semana(inst, 0) == list(range(inst.num_dias))
    assert vistas.color_modulo(inst, inst.bloques[0].modulo_id)\
        .startswith("#")


# --------------------------------------------------------------------------
# edicion
# --------------------------------------------------------------------------

def _reconstruir(inst, **cambios):
    tablas = dict(
        bloques=edicion.df_bloques(inst), docentes=edicion.df_docentes(inst),
        grupos=edicion.df_grupos(inst), salones=edicion.df_salones(inst),
        franjas=edicion.df_franjas(inst), pesos=edicion.df_pesos(inst),
        disp=edicion.disponibilidades(inst), vent=edicion.ventanas(inst))
    tablas.update(cambios)
    return edicion.instancia_desde_tablas(inst, **tablas)


@pytest.mark.parametrize("origen", ["sintetica", "mini"])
def test_ida_y_vuelta_instancia_tablas(sintetica, origen):
    inst = sintetica[0] if origen == "sintetica" else \
        mini_factible()["instancia"]
    assert _reconstruir(inst) == inst


def test_ida_y_vuelta_grillas(sintetica):
    inst, _ = sintetica
    for d in inst.docentes:
        df = edicion.df_grilla(inst, d.disponibilidad)
        assert df.shape == (inst.num_franjas, inst.num_dias)
        assert edicion.celdas_desde_grilla(df) == d.disponibilidad


def test_edicion_aplica_cambios(sintetica):
    inst, _ = sintetica
    bl = edicion.df_bloques(inst)
    bl.loc[0, "duracion"] = 1
    nueva = _reconstruir(inst, bloques=bl)
    assert nueva.bloques[0].duracion == 1
    assert nueva.bloques[1:] == inst.bloques[1:]


def test_edicion_errores_amigables(sintetica):
    inst, _ = sintetica
    bl = edicion.df_bloques(inst)
    bl.loc[0, "docente_id"] = "NO_EXISTE"
    with pytest.raises(ValueError, match="docente"):
        _reconstruir(inst, bloques=bl)
    bl = edicion.df_bloques(inst)
    bl.loc[0, "duracion"] = 999
    with pytest.raises(ValueError):
        _reconstruir(inst, bloques=bl)
    fr = edicion.df_franjas(inst)
    fr.loc[0, "inicio"] = "xx"
    with pytest.raises(ValueError, match="HH:MM"):
        _reconstruir(inst, franjas=fr)
    sa = edicion.df_salones(inst)
    sa = pd.concat([sa, sa.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="repetidos"):
        _reconstruir(inst, salones=sa)


def test_edicion_fila_nueva_y_vacia(sintetica):
    inst, _ = sintetica
    do = edicion.df_docentes(inst)
    do.loc[len(do)] = ["TNUEVO", "Nuevo", pd.NA]
    do.loc[len(do)] = ["", "", pd.NA]  # fila en blanco: se ignora
    nueva = _reconstruir(inst, docentes=do)
    assert len(nueva.docentes) == len(inst.docentes) + 1
    assert nueva.docente["TNUEVO"].disponibilidad == \
        edicion.todas_las_celdas(nueva)


def test_json_ida_y_vuelta(sintetica):
    inst, sol = sintetica
    inst2, sol2 = edicion.deserializar_json(
        edicion.serializar_json(inst, sol))
    assert inst2 == inst and sol2 == sol
    inst3, sol3 = edicion.deserializar_json(edicion.serializar_json(inst))
    assert inst3 == inst and sol3 is None
    with pytest.raises(ValueError):
        edicion.deserializar_json("{no es json")
    with pytest.raises(ValueError):
        edicion.deserializar_json('{"x": 1}')


# --------------------------------------------------------------------------
# ejecución y gráficas
# --------------------------------------------------------------------------

def test_ejecucion_y_cuadros(sintetica):
    inst, _ = sintetica
    lim = ejecucion.limites_desde(10, 5000)
    for algo in ("backtracking", "avara"):
        ej = ejecucion.ejecutar_construccion(inst, algo, None, lim)
        cuadros = ej.cuadros(50)
        assert 1 <= len(cuadros) <= 50
        assert cuadros[-1].asignacion == ej.resultado.asignacion
        fig = graficas.figura_proceso(cuadros, 0)
        assert fig.data is not None


def test_reparacion_y_comparar(sintetica):
    inst, sol = sintetica
    lim = ejecucion.limites_desde(10, 5000)
    ej = ejecucion.ejecutar_reparacion(inst, sol, "avara", None, lim,
                                       semilla=1, num_docentes=1)
    assert ej.escenario == "reparacion"
    assert "estabilidad" in ej.resultado.extra
    cuadros = ej.cuadros(30)
    assert cuadros[-1].asignacion == ej.resultado.asignacion
    assert len(cuadros_de_resultado(ej.resultado, ej.inicial or None)) >= len(
        cuadros)
    res = ejecucion.comparar(inst, [("backtracking", {}), ("beam", {})], lim)
    assert [e for e, ej2, err in res if ej2 and not err] == [
        "backtracking", "beam"]
    df = pd.DataFrame([ejecucion.fila_resumen(e, x) for e, x, _ in res])
    assert {"v", "f", "F", "tiempo_s", "terminado_por", "exito"} <= set(
        df.columns)
    assert graficas.figura_barras(df, "F", "F") is not None
    with pytest.raises(ValueError):
        ejecucion.ejecutar_reparacion(inst, {}, "avara")


def test_red_conflictos(sintetica):
    from planificador.core.conflictos import construir_conflictos
    inst, _ = sintetica
    assert graficas.red_conflictos(construir_conflictos(inst)) is not None


# --------------------------------------------------------------------------
# AppTest (humo)
# --------------------------------------------------------------------------

def _app_instancia():
    from planificador.app import pagina_instancia, sesion
    sesion.inicializar()
    pagina_instancia.render()


def _app_ejecutar():
    from planificador.app import pagina_ejecutar, sesion
    sesion.inicializar()
    pagina_ejecutar.render()


def _app_comparar():
    from planificador.app import pagina_comparar, sesion
    sesion.inicializar()
    pagina_comparar.render()


def _con_instancia(funcion, n=10):
    inst, sol = generar_instancia(n, 1, num_dias=4, num_franjas=6)
    at = AppTest.from_function(funcion, default_timeout=TIMEOUT)
    at.session_state["instancia"] = inst
    at.session_state["solucion_oculta"] = sol
    from planificador.core.conflictos import construir_conflictos
    at.session_state["conflictos"] = construir_conflictos(inst)
    at.session_state["version"] = 1
    return at.run()


def test_app_principal_carga():
    at = AppTest.from_file("../planificador/app/main.py",
                           default_timeout=TIMEOUT).run()
    assert not at.exception
    assert at.session_state["instancia"] is None
    at.button(key="gen_boton").click().run()
    assert not at.exception
    assert at.session_state["instancia"] is not None
    assert len(at.sidebar.markdown) >= 1


def test_pagina_instancia_generar_cargar_y_editar():
    at = AppTest.from_function(_app_instancia, default_timeout=TIMEOUT).run()
    assert not at.exception
    at.number_input(key="gen_n").set_value(10)
    at.button(key="gen_boton").click().run()
    assert not at.exception
    inst = at.session_state["instancia"]
    assert len(inst.bloques) == 10
    at.selectbox(key="sel_fixture").select("mini_factible").run()
    at.button(key="cargar_fixture").click().run()
    assert at.session_state["instancia"].nombre == "mini_factible"
    # aplicar sin cambios no debe fallar
    at.button(key="aplicar_cambios").click().run()
    assert not at.exception
    assert not at.error


def test_pagina_ejecutar_backtracking_y_avara():
    at = _con_instancia(_app_ejecutar)
    assert not at.exception
    for algo in ("backtracking", "avara"):
        at.selectbox(key="ej_algoritmo").select(algo).run()
        at.button(key="ej_boton").click().run()
        assert not at.exception, at.exception
        assert not at.error
        ej = at.session_state["ejecucion"]
        assert ej.algoritmo == algo
        n = at.session_state["_n_cuadros"]
        assert n >= 2
        at.slider(key="idx_cuadro").set_value(n // 2).run()
        assert not at.exception
        at.button(key="b_sig").click().run()
        assert at.session_state["idx_cuadro"] == n // 2 + 1
        at.button(key="b_fin").click().run()
        assert at.session_state["idx_cuadro"] == n - 1
        at.button(key="b_ini").click().run()
        assert at.session_state["idx_cuadro"] == 0
        at.selectbox(key="pr_vista").select("Docente").run()
        at.selectbox(key="pr_vista").select("Grupo").run()
        assert not at.exception


def test_pagina_ejecutar_reproducir_y_pausar():
    at = _con_instancia(_app_ejecutar)
    at.button(key="ej_boton").click().run()
    at.button(key="b_play").click().run()
    assert not at.exception
    assert at.session_state["reproduciendo"] is True
    at.button(key="b_pausa").click().run()
    assert at.session_state["reproduciendo"] is False


def test_pagina_ejecutar_reparacion():
    at = _con_instancia(_app_ejecutar)
    at.radio(key="ej_escenario").set_value("reparacion").run()
    at.selectbox(key="ej_algoritmo").select("avara").run()
    at.button(key="ej_boton").click().run()
    assert not at.exception, at.exception
    assert not at.error
    assert at.session_state["ejecucion"].escenario == "reparacion"


def test_pagina_ejecutar_reparacion_sin_vigente():
    inst = mini_reparacion()["instancia"]
    at = AppTest.from_function(_app_ejecutar, default_timeout=TIMEOUT)
    at.session_state["instancia"] = inst
    at.session_state["version"] = 1
    at.run()
    at.radio(key="ej_escenario").set_value("reparacion").run()
    assert not at.exception
    assert at.warning


def test_pagina_comparar_dos_algoritmos():
    at = _con_instancia(_app_comparar)
    assert not at.exception
    at.multiselect(key="cmp_algos").set_value(["backtracking", "avara"])
    at.button(key="cmp_boton").click().run()
    assert not at.exception, at.exception
    assert not at.error
    res = at.session_state["comparacion"]["resultados"]
    assert [e for e, ej, _ in res if ej] == ["backtracking", "avara"]
    assert len(at.dataframe) >= 1
