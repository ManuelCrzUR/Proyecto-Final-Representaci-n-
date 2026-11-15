"""Página «Ejecutar y animar»: corre un algoritmo y reproduce su búsqueda.

Animación: ``st.fragment(run_every=...)``. Mientras se reproduce, solo el
fragmento se vuelve a ejecutar cada ``1/velocidad`` s y avanza el índice en
``st.session_state`` antes de crear el slider; el resto de la página no se
recalcula. El botón Reproducir/Pausar hace un ``st.rerun()`` completo para
que el decorador reciba (o quite) ``run_every``. Al llegar al último cuadro
se pausa solo. No hay bucles con ``time.sleep`` que bloqueen el servidor.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from planificador.core.costo import desglose_f
from planificador.core.estado import Estado
from planificador.core.validador import validar

from . import componentes, ejecucion, graficas, sesion, vistas

ESCENARIOS = {"construccion": "Construcción desde cero",
              "reparacion": "Reparación (perturbar y reparar)"}
IDX = "idx_cuadro"


# --------------------------------------------------------------------------
# Formulario de ejecución
# --------------------------------------------------------------------------

def _formulario(inst) -> None:
    st.subheader("Configuración")
    algoritmo = componentes.selector_algoritmo("ej")
    with st.expander("Parámetros del algoritmo", expanded=True):
        params = componentes.widgets_parametros(algoritmo, "ej")
    seg, nodos = componentes.widgets_limites("ej")
    escenario = st.radio("Escenario", list(ESCENARIOS), horizontal=True,
                         format_func=ESCENARIOS.get, key="ej_escenario")
    pert = {}
    vigente = None
    if escenario == "reparacion":
        c = st.columns(3)
        pert = {"semilla": int(c[0].number_input("Semilla de perturbación",
                                                 0, 10**6, 0, key="ej_ps")),
                "num_docentes": int(c[1].number_input(
                    "Docentes afectados", 1, max(1, len(inst.docentes)), 1,
                    key="ej_pd")),
                "fraccion": float(c[2].slider(
                    "Fracción de celdas quitadas", 0.1, 1.0, 0.5, 0.1,
                    key="ej_pf"))}
        vigente = st.session_state.get("solucion_oculta") or (
            st.session_state.get("ultima_solucion"))
        if vigente:
            origen = ("solución oculta" if st.session_state.get(
                "solucion_oculta") else "última solución obtenida")
            st.caption(f"Horario vigente: {origen} ({len(vigente)} bloques).")
        else:
            st.warning("No hay horario vigente: la instancia no tiene "
                       "solución oculta y aún no has construido uno. "
                       "Ejecuta primero una construcción.")
    if st.button("Ejecutar", type="primary", key="ej_boton",
                 disabled=(escenario == "reparacion" and not vigente)):
        lim = ejecucion.limites_desde(seg, nodos)
        try:
            with st.spinner("Ejecutando..."):
                if escenario == "construccion":
                    ej = ejecucion.ejecutar_construccion(
                        inst, algoritmo, params, lim)
                else:
                    ej = ejecucion.ejecutar_reparacion(
                        inst, vigente, algoritmo, params, lim, **pert)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Falló la ejecución: {type(exc).__name__}: {exc}")
        else:
            st.session_state["ejecucion"] = ej
            st.session_state["version_ejecucion"] = st.session_state[
                "version"]
            st.session_state[IDX] = 0
            st.session_state["reproduciendo"] = False
            if escenario == "construccion":
                st.session_state["ultima_solucion"] = dict(
                    ej.resultado.asignacion)


# --------------------------------------------------------------------------
# Proceso de búsqueda
# --------------------------------------------------------------------------

def _cuadros(ej, max_cuadros: int) -> list:
    """Cuadros muestreados, cacheados en sesión (no se recalculan al animar)."""
    clave = (ej.uid, max_cuadros)
    cache = st.session_state.get("_cuadros")
    if not cache or cache[0] != clave:
        cache = (clave, ej.cuadros(max_cuadros))
        st.session_state["_cuadros"] = cache
    return cache[1]


def _mover(delta=None, absoluto=None) -> None:
    """Callback de los botones de navegación."""
    n = st.session_state.get("_n_cuadros", 1)
    actual = st.session_state.get(IDX, 0)
    nuevo = absoluto if absoluto is not None else actual + delta
    st.session_state[IDX] = max(0, min(n - 1, nuevo))
    st.session_state["reproduciendo"] = False


def _panel_estado(inst, cuadro, n_total: int) -> None:
    ev = cuadro.evento
    st.markdown(f"**Evento: `{ev.tipo}`** (paso {ev.paso})")
    st.caption(vistas.EXPLICACIONES.get(ev.tipo, ""))
    if ev.nota:
        st.write(f"Nota: {ev.nota}")
    if ev.bloque:
        txt = f"Bloque **{ev.bloque}**"
        if ev.posicion is not None:
            p = ev.posicion
            txt += f" en día {p.dia}, franja {p.franja}, salón {p.salon}"
        st.markdown(txt)
    filas = {
        "Profundidad": ev.profundidad,
        "Tamaño de frontera": ev.tam_frontera,
        "F": None if ev.F is None else round(ev.F, 3),
        "v": ev.v,
        "f": None if ev.f is None else round(ev.f, 3),
    }
    st.table(pd.DataFrame(
        {"valor": ["-" if x is None else str(x) for x in filas.values()]},
        index=list(filas)))
    st.progress(len(cuadro.asignacion) / max(1, n_total),
                text=f"Bloques ubicados: {len(cuadro.asignacion)} / "
                     f"{n_total}")


def _proceso(ej_uid: int) -> None:
    """Fragmento: controles, grilla, estado interno y gráfica."""
    ej = st.session_state["ejecucion"]
    cuadros = _cuadros(ej, st.session_state.get("max_cuadros", 300))
    n = len(cuadros)
    st.session_state["_n_cuadros"] = n
    inst = ej.instancia
    if st.session_state.get("reproduciendo"):
        if st.session_state.get(IDX, 0) >= n - 1:
            st.session_state["reproduciendo"] = False
            st.rerun()
        else:
            st.session_state[IDX] = st.session_state.get(IDX, 0) + 1
    st.session_state[IDX] = max(0, min(n - 1, st.session_state.get(IDX, 0)))
    if n > 1:
        st.slider("Cuadro", 0, n - 1, key=IDX)
    else:
        st.caption("La traza tiene un solo cuadro.")
    b = st.columns([1, 1, 1, 1, 2])
    b[0].button("⏮", on_click=_mover, kwargs={"absoluto": 0}, key="b_ini",
                help="Primer cuadro")
    b[1].button("◀", on_click=_mover, kwargs={"delta": -1}, key="b_ant",
                help="Cuadro anterior")
    b[2].button("▶", on_click=_mover, kwargs={"delta": 1}, key="b_sig",
                help="Cuadro siguiente")
    b[3].button("⏭", on_click=_mover, kwargs={"absoluto": n - 1},
                key="b_fin", help="Último cuadro")
    if st.session_state.get("reproduciendo"):
        if b[4].button("⏸ Pausar", key="b_pausa"):
            st.session_state["reproduciendo"] = False
            st.rerun()
    elif b[4].button("▶ Reproducir", key="b_play", disabled=n < 2):
        if st.session_state.get(IDX, 0) >= n - 1:
            st.session_state[IDX] = 0
        st.session_state["reproduciendo"] = True
        st.rerun()
    cuadro = cuadros[st.session_state[IDX]]
    vista, entidad, dias = componentes.selector_vista(inst, "pr")
    izq, der = st.columns([3, 2])
    with izq:
        resumen = componentes.mostrar_grilla(
            inst, cuadro.asignacion, vista, entidad,
            resaltado=cuadro.resaltado, dias=dias, conflictos=ej.conflictos)
        st.caption(
            "Borde azul = bloque del evento. Rojo = viola disponibilidad, "
            "ventana o cruce. Problemas en este cuadro: "
            f"{resumen['disponibilidad']} de disponibilidad, "
            f"{resumen['ventana']} de ventana, "
            f"{resumen['conflicto']} cruces.")
    with der:
        _panel_estado(inst, cuadro, len(inst.bloques))
    st.plotly_chart(graficas.figura_proceso(cuadros, st.session_state[IDX]),
                    width="stretch", key="grafica_proceso")


def _tab_proceso(ej) -> None:
    c = st.columns(2)
    c[0].slider("Velocidad (cuadros/s)", 1, 20, 4, key="velocidad")
    c[1].slider("Máximo de cuadros muestreados", 20, 2000, 300, 20,
                key="max_cuadros")
    tr = ej.resultado.traza
    if tr.truncada:
        st.warning(f"La traza se truncó: {tr.descartados} eventos "
                   "descartados por el tope.")
    periodo = (1.0 / st.session_state["velocidad"]
               if st.session_state.get("reproduciendo") else None)
    st.fragment(run_every=periodo)(_proceso)(ej.uid)


# --------------------------------------------------------------------------
# Solución final
# --------------------------------------------------------------------------

def _tab_final(ej) -> None:
    r = ej.resultado
    inst = ej.instancia
    st.caption(f"Algoritmo: **{r.algoritmo}** — parámetros: "
               f"{ej.parametros or 'por defecto'}")
    c = st.columns(5)
    c[0].metric("v (violaciones)", r.v)
    c[1].metric("f (blandas)", f"{r.f:.2f}")
    c[2].metric("F = f + λv", f"{r.F:.2f}")
    c[3].metric("Tiempo (s)", f"{r.tiempo_s:.3f}")
    c[4].metric("Terminado por", r.terminado_por)
    st.write(f"Nodos expandidos: {r.nodos_expandidos}, generados: "
             f"{r.nodos_generados}. Éxito: {'sí' if r.exito else 'no'}.")
    d1, d2 = st.columns(2)
    with d1:
        st.markdown("**Desglose de v**")
        vio = r.violaciones
        st.table(pd.DataFrame({"cantidad": {
            "sin ubicar": vio.sin_ubicar,
            "disponibilidad": vio.disponibilidad,
            "ventana": vio.ventana, "conflicto": vio.conflicto,
            "salón": vio.salon}}))
    with d2:
        st.markdown("**Desglose de f**")
        try:
            phi = desglose_f(Estado(inst, r.asignacion))
            st.table(pd.DataFrame(
                [{"φ": round(v, 3), "peso": getattr(inst.pesos, k, 1.0),
                  "w·φ": round(v * getattr(inst.pesos, k, 1.0), 3)}
                 for k, v in phi.items()], index=list(phi)))
        except Exception as exc:  # noqa: BLE001
            st.error(f"No se pudo desglosar f: {exc}")
    movidos = frozenset()
    if ej.escenario == "reparacion":
        movidos = vistas.bloques_movidos(ej.vigente, r.asignacion)
        e = r.extra
        m = st.columns(4)
        m[0].metric("Bloques inválidos", e.get("invalidos", "-"))
        m[1].metric("Bloques movidos", e.get("movidos", len(movidos)))
        m[2].metric("Estabilidad", f"{e.get('estabilidad', 0):.1%}")
        m[3].metric("Intentos / radio", f"{e.get('intentos', '-')} / "
                                        f"{e.get('radio', '-')}")
    st.markdown("**Horario final**")
    vista, entidad, dias = componentes.selector_vista(inst, "fin")
    componentes.mostrar_grilla(
        inst, r.asignacion, vista, entidad, movidos=movidos, dias=dias,
        conflictos=ej.conflictos)
    if ej.escenario == "reparacion":
        st.caption("Borde naranja discontinuo = bloque movido respecto al "
                   "horario vigente.")
        if movidos:
            st.write("Movidos: " + ", ".join(sorted(movidos)))
    rep = validar(inst, r.asignacion)
    st.markdown("**Reporte del validador**")
    if rep.problemas:
        st.warning(f"{len(rep.problemas)} problema(s) detectados.")
        with st.expander("Ver problemas", expanded=len(rep.problemas) <= 10):
            for p in rep.problemas[:200]:
                st.write("- " + p)
            if len(rep.problemas) > 200:
                st.caption(f"... y {len(rep.problemas) - 200} más.")
    else:
        st.success("El validador no encontró problemas.")


def render() -> None:
    """Dibuja la página."""
    st.title("Ejecutar y animar")
    inst = sesion.instancia()
    if inst is None:
        st.info("Primero genera o carga una instancia en la página "
                "«Instancia».")
        return
    _formulario(inst)
    ej = st.session_state.get("ejecucion")
    if ej is None:
        return
    st.divider()
    if st.session_state.get("version_ejecucion") != st.session_state[
            "version"]:
        st.warning("La instancia cambió desde esta ejecución; se muestran "
                   "los resultados anteriores.")
    st.caption(f"Resultado de {ej.algoritmo} ({ESCENARIOS[ej.escenario]}) "
               f"sobre «{ej.instancia.nombre}».")
    t1, t2 = st.tabs(["Proceso de búsqueda", "Solución final"])
    with t1:
        try:
            _tab_proceso(ej)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Error al dibujar el proceso: {exc}")
    with t2:
        try:
            _tab_final(ej)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Error al dibujar la solución: {exc}")
