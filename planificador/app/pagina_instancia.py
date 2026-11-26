"""Página de configuración de instancias del planificador."""

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
    """Genera y almacena instancias según sus parámetros."""
    return generar_instancia(
        n,
        semilla,
        num_dias=dias,
        num_franjas=franjas,
        garantizar_factible=factible,
        **DIFICULTADES[dificultad],
    )


def _fixtures() -> dict:
    """Obtiene las instancias pequeñas de demostración."""
    from planificador.datos_demo import TODAS_LAS_FIXTURES

    salida = {}

    for fabrica in TODAS_LAS_FIXTURES:
        d = fabrica()
        sol = d.get("solucion_vigente") or d.get("solucion")

        salida[d["instancia"].nombre] = (
            d["instancia"],
            sol,
            d.get("descripcion", ""),
        )

    return salida


def _fijar_y_recargar(inst, sol, mensaje: str) -> None:
    """Instala una instancia y actualiza la interfaz."""
    sesion.fijar_instancia(inst, sol)
    st.session_state["_flash"] = mensaje
    st.rerun()


def _seccion_generar() -> None:
    """Formulario de generación de instancias."""

    with st.container(border=True):
        st.subheader("01 · Generar instancia sintética")

        st.caption(
            "Configura las características del entorno "
            "para crear una nueva instancia del problema."
        )

        c = st.columns(4)

        n = c[0].number_input(
            "Bloques",
            2,
            400,
            20,
            key="gen_n",
        )

        semilla = c[1].number_input(
            "Semilla",
            0,
            10**6,
            0,
            key="gen_semilla",
        )

        dias = c[2].number_input(
            "Días",
            1,
            30,
            6,
            key="gen_dias",
        )

        franjas = c[3].number_input(
            "Franjas por día",
            2,
            16,
            8,
            key="gen_franjas",
        )

        c2 = st.columns([1, 1.5])

        dif = c2[0].selectbox(
            "Dificultad",
            list(DIFICULTADES),
            index=1,
            key="gen_dif",
            help=(
                "Holgada: mayor disponibilidad. "
                "Ajustada: menor disponibilidad."
            ),
        )

        factible = c2[1].checkbox(
            "Garantizar factibilidad (solución de referencia)",
            value=True,
            key="gen_factible",
        )

        st.write("")

        if st.button(
            "Generar nueva instancia",
            type="primary",
            key="gen_boton",
            use_container_width=False,
        ):
            try:
                with st.spinner("Generando instancia..."):
                    inst, sol = _generar(
                        int(n),
                        int(semilla),
                        int(dias),
                        int(franjas),
                        dif,
                        factible,
                    )

            except Exception as exc:  # noqa: BLE001
                st.error(f"No se pudo generar la instancia: {exc}")

            else:
                _fijar_y_recargar(
                    inst,
                    sol,
                    f"Instancia «{inst.nombre}» generada correctamente.",
                )


def _seccion_cargar() -> None:
    """Carga instancias desde JSON o desde ejemplos."""

    with st.container(border=True):
        st.subheader("02 · Cargar y guardar")

        st.caption(
            "Carga una instancia existente o descarga "
            "la instancia actual para utilizarla posteriormente."
        )

        c1, c2 = st.columns(2)

        with c1:
            st.markdown("**Cargar desde archivo JSON**")

            archivo = st.file_uploader(
                "Selecciona un archivo",
                type="json",
                key="subida_json",
            )

            if archivo is not None:
                if st.button(
                    "Cargar instancia",
                    key="usar_json",
                ):
                    try:
                        inst, sol = edicion.deserializar_json(
                            archivo.getvalue()
                        )

                    except ValueError as exc:
                        st.error(str(exc))

                    else:
                        _fijar_y_recargar(
                            inst,
                            sol,
                            f"Instancia «{inst.nombre}» cargada.",
                        )

            with st.expander("Ver instancias de demostración"):
                fix = _fixtures()

                if fix:
                    nombre = st.selectbox(
                        "Seleccionar ejemplo",
                        list(fix),
                        key="sel_fixture",
                    )

                    st.caption(fix[nombre][2])

                    if st.button(
                        "Cargar ejemplo",
                        key="cargar_fixture",
                    ):
                        _fijar_y_recargar(
                            fix[nombre][0],
                            fix[nombre][1],
                            f"Instancia de demostración «{nombre}» cargada.",
                        )

                else:
                    st.info("No hay instancias de demostración disponibles.")

        with c2:
            st.markdown("**Descargar instancia actual**")

            inst = sesion.instancia()

            if inst is not None:
                st.write(
                    "Guarda la configuración actual en formato JSON."
                )

                st.download_button(
                    "Descargar instancia (JSON)",
                    edicion.serializar_json(
                        inst,
                        st.session_state.get("solucion_oculta"),
                    ),
                    file_name=f"{inst.nombre}.json",
                    mime="application/json",
                    key="descarga_json",
                    use_container_width=True,
                )

            else:
                st.info(
                    "Primero genera o carga una instancia "
                    "para habilitar la descarga."
                )


def _seccion_gamma(inst: Instancia) -> None:
    """Muestra las estadísticas del grafo de conflictos."""

    with st.container(border=True):
        st.subheader("03 · Grafo de conflictos")

        st.caption(
            "El grafo Γ representa las relaciones de conflicto "
            "entre los bloques que comparten docentes o grupos."
        )

        aristas, medio, maximo = sesion.estadisticas_gamma(
            st.session_state.get("conflictos")
        )

        c = st.columns(3)

        c[0].metric("Aristas", aristas)
        c[1].metric("Grado medio", f"{medio:.2f}")
        c[2].metric("Grado máximo", maximo)

        if len(inst.bloques) <= 80:
            with st.expander("Visualizar grafo de conflictos"):
                st.plotly_chart(
                    graficas.red_conflictos(
                        st.session_state["conflictos"]
                    ),
                    width="stretch",
                )

        else:
            st.caption(
                "La visualización del grafo está disponible "
                "para instancias de hasta 80 bloques."
            )


def _editor_grilla(
    inst,
    etiqueta,
    ids,
    almacen,
    clave,
    version,
) -> None:
    """Editor de grilla de días y franjas."""

    if not ids:
        st.caption("No hay entidades disponibles.")
        return

    sel = st.selectbox(
        etiqueta,
        ids,
        key=f"{clave}_sel_{version}",
    )

    celdas = almacen.get(sel)

    if celdas is None:
        celdas = edicion.todas_las_celdas(inst)

    df = edicion.df_grilla(inst, celdas)

    editado = st.data_editor(
        df,
        key=f"{clave}_grid_{version}_{sel}",
        width="stretch",
    )

    almacen[sel] = edicion.celdas_desde_grilla(editado)


def _seccion_edicion(inst: Instancia) -> None:
    """Editor de los componentes de la instancia."""

    with st.container(border=True):
        st.subheader("04 · Editor de la instancia")

        st.caption(
            "Modifica los bloques, docentes, grupos, salones, "
            "franjas horarias y pesos de la función de costo. "
            "Al finalizar, pulsa Aplicar cambios."
        )

        v = st.session_state["version"]

        if st.session_state.get("_edic_version") != v:
            st.session_state["_edic_version"] = v
            st.session_state["_disp"] = edicion.disponibilidades(inst)
            st.session_state["_vent"] = edicion.ventanas(inst)

        disp = st.session_state["_disp"]
        vent = st.session_state["_vent"]

        t_bl, t_do, t_gr, t_sa, t_fr, t_pe = st.tabs(
            [
                "Bloques",
                "Docentes",
                "Grupos",
                "Salones",
                "Franjas",
                "Pesos",
            ]
        )

        cfg_texto = st.column_config.TextColumn

        with t_bl:
            st.caption("Información de los bloques académicos.")

            bloques = st.data_editor(
                edicion.df_bloques(inst),
                num_rows="dynamic",
                key=f"ed_bloques_{v}",
                width="stretch",
                column_config={
                    "duracion": st.column_config.NumberColumn(
                        "duracion",
                        min_value=1,
                        step=1,
                    ),
                    "tipo_sesion": st.column_config.SelectboxColumn(
                        "tipo_sesion",
                        options=list(edicion.TIPOS_SESION),
                    ),
                    "grupos": cfg_texto(
                        "grupos",
                        help="IDs de los grupos separados por coma.",
                    ),
                },
            )

        with t_do:
            st.caption("Información y disponibilidad de los docentes.")

            docentes = st.data_editor(
                edicion.df_docentes(inst),
                num_rows="dynamic",
                key=f"ed_docentes_{v}",
                width="stretch",
            )

            st.markdown("**Disponibilidad de docentes (A)**")

            _editor_grilla(
                inst,
                "Seleccionar docente",
                [d.id for d in inst.docentes],
                disp,
                "disp",
                v,
            )

        with t_gr:
            st.caption("Información y ventanas horarias de los grupos.")

            grupos = st.data_editor(
                edicion.df_grupos(inst),
                num_rows="dynamic",
                key=f"ed_grupos_{v}",
                width="stretch",
            )

            st.markdown("**Ventana horaria de los grupos (W)**")

            _editor_grilla(
                inst,
                "Seleccionar grupo",
                [g.id for g in inst.grupos],
                vent,
                "vent",
                v,
            )

        with t_sa:
            st.caption("Características y capacidad de los salones.")

            salones = st.data_editor(
                edicion.df_salones(inst),
                num_rows="dynamic",
                key=f"ed_salones_{v}",
                width="stretch",
            )

        with t_fr:
            st.caption("Configuración de los días y franjas horarias.")

            franjas = st.data_editor(
                edicion.df_franjas(inst),
                num_rows="dynamic",
                key=f"ed_franjas_{v}",
                width="stretch",
            )

            st.caption(
                "Utiliza el formato HH:MM. "
                "Si cambias el número de franjas, revisa "
                "la disponibilidad y las ventanas."
            )

        with t_pe:
            st.caption("Pesos utilizados en la función de costo.")

            pesos = st.data_editor(
                edicion.df_pesos(inst),
                key=f"ed_pesos_{v}",
                width="stretch",
            )

            st.caption("Si λ (lam) está vacío, se calcula automáticamente.")

        st.divider()

        nombre = st.text_input(
            "Nombre de la instancia",
            inst.nombre,
            key=f"ed_nombre_{v}",
        )

        if st.button(
            "Aplicar cambios",
            type="primary",
            key="aplicar_cambios",
        ):
            try:
                nueva = edicion.instancia_desde_tablas(
                    inst,
                    bloques=bloques,
                    docentes=docentes,
                    grupos=grupos,
                    salones=salones,
                    franjas=franjas,
                    pesos=pesos,
                    disp=disp,
                    vent=vent,
                    nombre=nombre or inst.nombre,
                )

            except (ValueError, KeyError, TypeError) as exc:
                st.error(f"No se pudieron aplicar los cambios: {exc}")

            else:
                _fijar_y_recargar(
                    nueva,
                    None,
                    "Cambios aplicados. La solución de referencia "
                    "se descartó porque la instancia fue modificada.",
                )


def render() -> None:
    """Construye la página de configuración de instancias."""

    st.title("Instancias")

    st.markdown(
        "Genera, carga, consulta y modifica las instancias "
        "del planificador académico."
    )

    flash = st.session_state.pop("_flash", None)

    if flash:
        st.success(flash)

    _seccion_generar()
    _seccion_cargar()

    inst = sesion.instancia()

    if inst is None:
        st.info(
            "Para comenzar, genera una instancia sintética "
            "o carga una configuración existente."
        )
        return

    with st.container(border=True):
        st.subheader("Resumen de la instancia")

        st.markdown(f"**{inst.nombre}**")

        st.caption(
            f"Horizonte: {inst.num_dias} días × "
            f"{inst.num_franjas} franjas."
        )

        c = st.columns(4)

        c[0].metric("Bloques", len(inst.bloques))
        c[1].metric("Docentes", len(inst.docentes))
        c[2].metric("Grupos", len(inst.grupos))
        c[3].metric("Salones", len(inst.salones))

        if st.session_state.get("solucion_oculta"):
            st.caption(
                "La instancia tiene una solución de referencia "
                "generada sintéticamente."
            )

    _seccion_gamma(inst)
    _seccion_edicion(inst)

