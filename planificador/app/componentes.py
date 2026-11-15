"""Widgets reutilizables de las páginas (parámetros, límites, grillas)."""

from __future__ import annotations

import streamlit as st

from planificador.algoritmos.registro import NOMBRES, REGISTRO

from . import vistas


def selector_algoritmo(clave: str) -> str:
    """Selector de algoritmo con su descripción."""
    nombre = st.selectbox("Algoritmo", NOMBRES, key=f"{clave}_algoritmo")
    st.caption(REGISTRO[nombre].descripcion)
    return nombre


def widgets_parametros(nombre: str, clave: str) -> dict:
    """Widgets de los parámetros ``ajustables`` del algoritmo."""
    entrada = REGISTRO[nombre]
    valores = {}
    for p, (tipo, extra) in entrada.ajustables.items():
        defecto = entrada.parametros[p]
        k = f"{clave}_{nombre}_{p}"
        if tipo == "opcion":
            valores[p] = st.selectbox(p, extra, key=k,
                                      index=list(extra).index(defecto))
        elif tipo == "bool":
            valores[p] = st.checkbox(p, value=defecto, key=k)
        elif tipo == "int":
            valores[p] = st.slider(p, int(extra[0]), int(extra[1]),
                                   int(defecto), key=k)
        elif tipo == "float":
            valores[p] = st.slider(p, float(extra[0]), float(extra[1]),
                                   float(defecto), key=k)
        else:
            valores[p] = defecto
    return valores


def widgets_limites(clave: str) -> tuple:
    """``(max_segundos, max_nodos)``; 0 = sin límite."""
    c1, c2 = st.columns(2)
    seg = c1.number_input("Límite de tiempo (s)", 0.0, 3600.0, 10.0, 1.0,
                          key=f"{clave}_seg", help="0 = sin límite")
    nodos = c2.number_input("Límite de nodos", 0, 10_000_000, 50_000, 1000,
                            key=f"{clave}_nodos", help="0 = sin límite")
    return seg, nodos


def selector_vista(inst, clave: str, columnas: bool = True) -> tuple:
    """Vista (salón/docente/grupo), entidad y días (semana) a mostrar."""
    c1, c2, c3 = st.columns(3)
    vista = c1.selectbox("Vista", vistas.VISTAS, key=f"{clave}_vista")
    ents = vistas.entidades(inst, vista)
    entidad = c2.selectbox(vista, ents, key=f"{clave}_ent_{vista}") \
        if ents else None
    sem = vistas.semanas(inst)
    dias = None
    if len(sem) > 1:
        s = c3.selectbox("Semana", sem, key=f"{clave}_semana")
        dias = vistas.dias_de_semana(inst, s)
    return vista, entidad, dias


def mostrar_grilla(inst, asignacion: dict, vista: str, entidad: str | None,
                   *, resaltado=None, movidos=frozenset(), dias=None,
                   conflictos=None, compacta: bool = False) -> dict:
    """Dibuja la grilla y devuelve el resumen de marcas del horario entero."""
    marcas = vistas.violaciones_por_celda(inst, asignacion, conflictos)
    if entidad is None:
        st.info("No hay entidades para esta vista.")
        return vistas.resumen_marcas(marcas)
    g = vistas.construir_grilla(inst, asignacion, vista, entidad,
                                resaltado=resaltado, movidos=movidos,
                                dias=dias, marcas=marcas)
    st.markdown(vistas.grilla_a_html(g, compacta), unsafe_allow_html=True)
    return vistas.resumen_marcas(marcas)
