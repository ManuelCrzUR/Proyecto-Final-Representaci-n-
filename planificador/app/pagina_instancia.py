"""Página «Instancia»: generar, cargar, editar y guardar instancias."""

from __future__ import annotations

import streamlit as st

from planificador.core.modelo import Instancia
from planificador.io_datos.sintetico import generar_instancia

from . import edicion, graficas, sesion

DIFICULTADES = {
    "Holgada": {"prob_disponible": 0.7, "prob_ventana": 0.9},
    "Media": {"prob_disponible": 0.5, "prob_ventana": 0.7},
    "Ajustada": {"prob_disponible": 0.3, "prob_ventana": 0.5},
}


@st.cache_data(show_spinner=False, max_entries=16)
def _generar(n, semilla, dias, franjas, dificultad, factible):
    """Generación cacheada por argumentos primitivos (hashables)."""
    return generar_instancia(
        n, semilla, num_dias=dias, num_franjas=franjas,
        garantizar_factible=factible, **DIFICULTADES[dificultad])


def _fixtures() -> dict:
    """Fixtures mini disponibles (vacío si ``tests`` no está importable)."""
    try:
        from tests.fixtures.instancias_mini import TODAS_LAS_FIXTURES
    except ImportError:
        return {}
    salida = {}
    for fabrica in TODAS_LAS_FIXTURES:
        d = fabrica()
        sol = d.get("solucion_vigente") or d.get("solucion")
        salida[d["instancia"].nombre] = (d["instancia"], sol,
                                         d.get("descripcion", ""))
    return salida


def _fijar_y_recargar(inst, sol, mensaje: str) -> None:
    """Instala la instancia y recarga para refrescar la barra lateral."""
    sesion.fijar_instancia(inst, sol)
    st.session_state["_flash"] = mensaje
    st.rerun()


def _seccion_generar() -> None:
    st.subheader("Generar instancia sintética")
    c = st.columns(4)
    n = c[0].number_input("Bloques", 2, 400, 20, key="gen_n")
    semilla = c[1].number_input("Semilla", 0, 10**6, 0, key="gen_semilla")
    dias = c[2].number_input("Días", 1, 30, 6, key="gen_dias")
    franjas = c[3].number_input("Franjas por día", 2, 16, 8,
                                key="gen_franjas")
    c2 = st.columns(2)
    dif = c2[0].selectbox("Dificultad", list(DIFICULTADES), index=1,
                          key="gen_dif",
                          help="Holgada = más disponibilidad; ajustada = "
                               "menos.")
    factible = c2[1].checkbox("Garantizar factibilidad (solución oculta)",
                              value=True, key="gen_factible")
    if st.button("Generar instancia", type="primary", key="gen_boton"):
        try:
            with st.spinner("Generando..."):
                inst, sol = _generar(int(n), int(semilla), int(dias),
                                     int(franjas), dif, factible)
        except Exception as exc:  # noqa: BLE001
            st.error(f"No se pudo generar la instancia: {exc}")
        else:
            _fijar_y_recargar(inst, sol,
                              f"Instancia «{inst.nombre}» generada.")


def _seccion_cargar() -> None:
    st.subheader("Cargar / guardar")
    c1, c2 = st.columns(2)
    with c1:
        archivo = st.file_uploader("Cargar instancia (JSON)", type="json",
                                   key="subida_json")
        if archivo is not None and st.button("Usar archivo cargado",
                                             key="usar_json"):
            try:
                inst, sol = edicion.deserializar_json(archivo.getvalue())
            except ValueError as exc:
                st.error(str(exc))
            else:
                _fijar_y_recargar(inst, sol,
                                  f"Instancia «{inst.nombre}» cargada.")
        fix = _fixtures()
        if fix:
            nombre = st.selectbox("Fixtures mini (demos pequeñas)",
                                  list(fix), key="sel_fixture")
            st.caption(fix[nombre][2])
            if st.button("Cargar fixture", key="cargar_fixture"):
                _fijar_y_recargar(fix[nombre][0], fix[nombre][1],
                                  f"Fixture «{nombre}» cargado.")
    with c2:
        inst = sesion.instancia()
        if inst is not None:
            st.download_button(
                "Descargar instancia (JSON)",
                edicion.serializar_json(
                    inst, st.session_state.get("solucion_oculta")),
                file_name=f"{inst.nombre}.json", mime="application/json",
                key="descarga_json")
        st.file_uploader("Importar plantilla Excel (próximamente)",
                         disabled=True, key="subida_excel",
                         help="Llegará en el sprint 5.")


def _seccion_gamma(inst: Instancia) -> None:
    st.subheader("Grafo de conflictos Γ")
    aristas, medio, maximo = sesion.estadisticas_gamma(
        st.session_state.get("conflictos"))
    c = st.columns(3)
    c[0].metric("Aristas", aristas)
    c[1].metric("Grado medio", f"{medio:.2f}")
    c[2].metric("Grado máximo", maximo)
    if len(inst.bloques) <= 80:
        if st.checkbox("Mostrar grafo", key="ver_grafo"):
            st.plotly_chart(
                graficas.red_conflictos(st.session_state["conflictos"]),
                width="stretch")
    else:
        st.caption("El grafo solo se dibuja con 80 bloques o menos.")


def _editor_grilla(inst, etiqueta, ids, almacen, clave, version) -> None:
    """Editor de grilla días x franjas para una entidad seleccionada."""
    if not ids:
        st.caption("No hay entidades.")
        return
    sel = st.selectbox(etiqueta, ids, key=f"{clave}_sel_{version}")
    celdas = almacen.get(sel)
    if celdas is None:
        celdas = edicion.todas_las_celdas(inst)
    df = edicion.df_grilla(inst, celdas)
    editado = st.data_editor(df, key=f"{clave}_grid_{version}_{sel}",
                             width="stretch")
    almacen[sel] = edicion.celdas_desde_grilla(editado)


def _seccion_edicion(inst: Instancia) -> None:
    st.subheader("Edición de la instancia")
    st.caption("Edita las tablas y pulsa «Aplicar cambios». Los días del "
               "horizonte no se editan aquí (se fijan al generar).")
    v = st.session_state["version"]
    if st.session_state.get("_edic_version") != v:
        st.session_state["_edic_version"] = v
        st.session_state["_disp"] = edicion.disponibilidades(inst)
        st.session_state["_vent"] = edicion.ventanas(inst)
    disp, vent = st.session_state["_disp"], st.session_state["_vent"]
    t_bl, t_do, t_gr, t_sa, t_fr, t_pe = st.tabs(
        ["Bloques", "Docentes", "Grupos", "Salones", "Franjas", "Pesos"])
    cfg_texto = st.column_config.TextColumn
    with t_bl:
        bloques = st.data_editor(
            edicion.df_bloques(inst), num_rows="dynamic",
            key=f"ed_bloques_{v}", width="stretch",
            column_config={
                "duracion": st.column_config.NumberColumn(
                    "duracion", min_value=1, step=1),
                "tipo_sesion": st.column_config.SelectboxColumn(
                    "tipo_sesion", options=list(edicion.TIPOS_SESION)),
                "grupos": cfg_texto("grupos", help="ids separados por coma"),
            })
    with t_do:
        docentes = st.data_editor(
            edicion.df_docentes(inst), num_rows="dynamic",
            key=f"ed_docentes_{v}", width="stretch")
        st.markdown("**Disponibilidad A** (marca las celdas disponibles)")
        _editor_grilla(inst, "Docente", [d.id for d in inst.docentes],
                       disp, "disp", v)
    with t_gr:
        grupos = st.data_editor(
            edicion.df_grupos(inst), num_rows="dynamic",
            key=f"ed_grupos_{v}", width="stretch")
        st.markdown("**Ventana W** (celdas permitidas del grupo)")
        _editor_grilla(inst, "Grupo", [g.id for g in inst.grupos],
                       vent, "vent", v)
    with t_sa:
        salones = st.data_editor(
            edicion.df_salones(inst), num_rows="dynamic",
            key=f"ed_salones_{v}", width="stretch")
    with t_fr:
        franjas = st.data_editor(
            edicion.df_franjas(inst), num_rows="dynamic",
            key=f"ed_franjas_{v}", width="stretch")
        st.caption("Horas en formato HH:MM. Si cambias el número de "
                   "franjas, revisa después disponibilidad y ventanas.")
    with t_pe:
        pesos = st.data_editor(edicion.df_pesos(inst),
                               key=f"ed_pesos_{v}", width="stretch")
        st.caption("«lam» vacío = λ automático.")
    nombre = st.text_input("Nombre de la instancia", inst.nombre,
                           key=f"ed_nombre_{v}")
    if st.button("Aplicar cambios", type="primary", key="aplicar_cambios"):
        try:
            nueva = edicion.instancia_desde_tablas(
                inst, bloques=bloques, docentes=docentes, grupos=grupos,
                salones=salones, franjas=franjas, pesos=pesos,
                disp=disp, vent=vent, nombre=nombre or inst.nombre)
        except (ValueError, KeyError, TypeError) as exc:
            st.error(f"No se pudieron aplicar los cambios: {exc}")
        else:
            _fijar_y_recargar(
                nueva, None, "Cambios aplicados. La solución oculta se "
                "descartó porque la instancia cambió.")


def render() -> None:
    """Dibuja la página."""
    st.title("Instancia")
    flash = st.session_state.pop("_flash", None)
    if flash:
        st.success(flash)
    _seccion_generar()
    st.divider()
    _seccion_cargar()
    inst = sesion.instancia()
    if inst is None:
        st.info("Genera o carga una instancia para continuar.")
        return
    st.divider()
    st.success(f"Instancia actual: **{inst.nombre}** — "
               f"{len(inst.bloques)} bloques, {len(inst.docentes)} docentes, "
               f"{len(inst.grupos)} grupos, {len(inst.salones)} salones, "
               f"{inst.num_dias}×{inst.num_franjas} celdas.")
    _seccion_gamma(inst)
    st.divider()
    _seccion_edicion(inst)
