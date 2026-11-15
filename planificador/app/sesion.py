"""Estado de sesión compartido por las páginas de la interfaz."""

from __future__ import annotations

import streamlit as st

from planificador.core.conflictos import construir_conflictos
from planificador.core.modelo import Instancia


def inicializar() -> None:
    """Crea las claves de sesión que faltan."""
    st.session_state.setdefault("instancia", None)
    st.session_state.setdefault("solucion_oculta", None)
    st.session_state.setdefault("conflictos", None)
    st.session_state.setdefault("version", 0)
    st.session_state.setdefault("ejecucion", None)
    st.session_state.setdefault("ultima_solucion", None)
    st.session_state.setdefault("comparacion", None)


def instancia() -> Instancia | None:
    """Instancia actual (o None)."""
    return st.session_state.get("instancia")


def fijar_instancia(inst: Instancia, solucion: dict | None = None) -> None:
    """Instala una instancia nueva y descarta lo que dependía de la anterior."""
    st.session_state["instancia"] = inst
    st.session_state["solucion_oculta"] = solucion
    st.session_state["conflictos"] = construir_conflictos(inst)
    st.session_state["version"] = st.session_state.get("version", 0) + 1
    st.session_state["comparacion"] = None
    st.session_state["ultima_solucion"] = None


def estadisticas_gamma(conflictos: dict) -> tuple:
    """``(aristas, grado_medio, grado_max)`` de Γ."""
    if not conflictos:
        return 0, 0.0, 0
    grados = [len(v) for v in conflictos.values()]
    return sum(grados) // 2, sum(grados) / len(grados), max(grados)


def barra_lateral() -> None:
    """Resumen de la instancia actual en la barra lateral."""
    with st.sidebar:
        st.header("Instancia actual")
        inst = instancia()
        if inst is None:
            st.info("Aún no hay instancia. Genera o carga una en la "
                    "página «Instancia».")
            return
        st.markdown(f"**{inst.nombre}**")
        st.write(f"Bloques: {len(inst.bloques)}")
        st.write(f"Docentes: {len(inst.docentes)}")
        st.write(f"Grupos: {len(inst.grupos)}")
        st.write(f"Salones: {len(inst.salones)}")
        st.write(f"Horizonte: {inst.num_dias} días × "
                 f"{inst.num_franjas} franjas")
        aristas, medio, _ = estadisticas_gamma(
            st.session_state.get("conflictos"))
        st.write(f"Γ: {aristas} aristas, grado medio {medio:.1f}")
        if st.session_state.get("solucion_oculta"):
            st.caption("Solución oculta disponible (sintética).")
