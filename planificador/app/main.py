"""Punto de entrada de la interfaz.

Ejecutar desde la raíz del repo:
``.venv/bin/streamlit run planificador/app/main.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:  # streamlit solo agrega la carpeta del script
    sys.path.insert(0, str(RAIZ))

import streamlit as st  # noqa: E402

from planificador.app import (  # noqa: E402
    pagina_comparar,
    pagina_ejecutar,
    pagina_instancia,
    sesion,
)


def main() -> None:
    """Configura la página, la barra lateral y la navegación."""
    st.set_page_config(page_title="Planificador de horarios",
                       page_icon="📅", layout="wide")
    sesion.inicializar()
    sesion.barra_lateral()
    paginas = [
        st.Page(pagina_instancia.render, title="Instancia",
                url_path="instancia", default=True),
        st.Page(pagina_ejecutar.render, title="Ejecutar y animar",
                url_path="ejecutar"),
        st.Page(pagina_comparar.render, title="Comparar",
                url_path="comparar"),
    ]
    st.navigation(paginas).run()


main()
