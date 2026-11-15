"""Página «Comparar»: varios algoritmos sobre la misma instancia."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from planificador.algoritmos.registro import NOMBRES, REGISTRO

from . import componentes, ejecucion, graficas, sesion


@st.cache_data(show_spinner=False, max_entries=8)
def _leer_csv(contenido: bytes) -> pd.DataFrame:
    """Lee un CSV de experimentos (cacheado por su contenido)."""
    import io
    return pd.read_csv(io.BytesIO(contenido))


def _formulario(inst) -> None:
    st.subheader("Configuración")
    elegidos = st.multiselect("Algoritmos a comparar", NOMBRES,
                              default=list(NOMBRES[:2]), key="cmp_algos")
    editar = st.checkbox("Editar parámetros (si no, valores por defecto)",
                         key="cmp_editar")
    configs = []
    for nombre in elegidos:
        if editar and REGISTRO[nombre].ajustables:
            with st.expander(f"Parámetros de {nombre}"):
                params = componentes.widgets_parametros(nombre, "cmp")
        else:
            params = ejecucion.parametros_por_defecto(nombre)
        configs.append((nombre, params))
    seg, nodos = componentes.widgets_limites("cmp")
    if st.button("Comparar", type="primary", key="cmp_boton",
                 disabled=not elegidos):
        lim = ejecucion.limites_desde(seg, nodos)
        with st.spinner("Comparando..."):
            res = ejecucion.comparar(inst, configs, lim)
        st.session_state["comparacion"] = {
            "resultados": res, "version": st.session_state["version"]}


def _mostrar(inst, comp: dict) -> None:
    if comp["version"] != st.session_state["version"]:
        st.warning("La instancia cambió desde esta comparación.")
    ok = [(e, ej) for e, ej, err in comp["resultados"] if ej is not None]
    for etiqueta, _, err in comp["resultados"]:
        if err:
            st.error(f"{etiqueta} falló: {err}")
    if not ok:
        return
    df = pd.DataFrame([ejecucion.fila_resumen(e, ej) for e, ej in ok])
    st.subheader("Resultados")
    st.dataframe(df, width="stretch", hide_index=True)
    c = st.columns(3)
    c[0].plotly_chart(graficas.figura_barras(df, "tiempo_s", "Tiempo (s)"),
                      width="stretch", key="bar_tiempo")
    c[1].plotly_chart(
        graficas.figura_barras(df, "nodos_expandidos",
                               "Nodos expandidos (log)", log=True),
        width="stretch", key="bar_nodos")
    c[2].plotly_chart(graficas.figura_barras(df, "F", "F = f + λv"),
                      width="stretch", key="bar_F")
    st.subheader("Soluciones lado a lado")
    vista, entidad, dias = componentes.selector_vista(inst, "cmpv")
    cols = st.columns(len(ok))
    for col, (etiqueta, ej) in zip(cols, ok):
        with col:
            st.markdown(f"**{etiqueta}** (v={ej.resultado.v}, "
                        f"F={ej.resultado.F:.1f})")
            componentes.mostrar_grilla(
                inst, ej.resultado.asignacion, vista, entidad, dias=dias,
                conflictos=ej.conflictos, compacta=True)


def _seccion_csv() -> None:
    st.subheader("Resultados de experimentos (CSV)")
    archivo = st.file_uploader("Cargar CSV de salidas/experimentos/",
                               type="csv", key="cmp_csv")
    if archivo is None:
        return
    try:
        df = _leer_csv(archivo.getvalue())
    except Exception as exc:  # noqa: BLE001
        st.error(f"No se pudo leer el CSV: {exc}")
        return
    st.dataframe(df, width="stretch", hide_index=True)
    numericas = [c for c in df.columns if pd.api.types.is_numeric_dtype(
        df[c])]
    texto = [c for c in df.columns if c not in numericas]
    if not numericas or not texto:
        st.info("El CSV necesita al menos una columna de texto y una "
                "numérica para graficar.")
        return
    c1, c2 = st.columns(2)
    grupo = c1.selectbox("Agrupar por", texto, key="csv_grupo")
    valor = c2.selectbox("Métrica (media)", numericas, key="csv_valor")
    agg = df.groupby(grupo, as_index=False)[valor].mean()
    agg = agg.rename(columns={grupo: "algoritmo"})
    st.plotly_chart(graficas.figura_barras(agg, valor, f"{valor} por {grupo}"),
                    width="stretch", key="csv_barras")


def render() -> None:
    """Dibuja la página."""
    st.title("Comparar algoritmos")
    inst = sesion.instancia()
    if inst is None:
        st.info("Primero genera o carga una instancia en la página "
                "«Instancia».")
    else:
        _formulario(inst)
        comp = st.session_state.get("comparacion")
        if comp:
            try:
                _mostrar(inst, comp)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Error al mostrar la comparación: {exc}")
    st.divider()
    _seccion_csv()
