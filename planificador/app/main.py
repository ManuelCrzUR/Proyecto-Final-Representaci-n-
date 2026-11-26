"""Punto de entrada de la interfaz del planificador de horarios."""

from __future__ import annotations

import base64
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import streamlit as st  # noqa: E402

from planificador.app import (  # noqa: E402
    pagina_comparar,
    pagina_ejecutar,
    pagina_instancia,
    sesion,
)


ASSETS = Path(__file__).resolve().parent / "assets"


CSS = """
<style>
:root {
    color-scheme: dark;
}

.stApp,
[data-testid="stAppViewContainer"] {
    background: #252431;
    color: #f5f3fc;
    font-family: "Segoe UI", Arial, sans-serif;
}

/* Encabezado general */

[data-testid="stHeader"] {
    background: rgba(37, 36, 49, 0.94);
}

[data-testid="stMainBlockContainer"] {
    max-width: 1450px;
    padding: 1.8rem 3rem 3rem;
}

.brand-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 25px;
    padding: 17px 22px;
    margin-bottom: 30px;
    background: linear-gradient(120deg, #302e3f, #292735);
    border: 1px solid #494356;
    border-radius: 16px;
    box-shadow: 0 12px 35px rgba(0, 0, 0, 0.16);
}

.brand-logos {
    display: flex;
    align-items: center;
    gap: 17px;
    padding: 8px 13px;
    background: #faf9fd;
    border-radius: 10px;
}

.brand-logos img {
    display: block;
    object-fit: contain;
}

.brand-urosario {
    width: 155px;
    height: 48px;
}

.brand-macc {
    width: 105px;
    height: 42px;
    border-left: 1px solid #ded9e7;
    padding-left: 14px;
}

.brand-text {
    text-align: right;
    color: #bdb5ce;
    font-size: 10px;
    line-height: 1.9;
    letter-spacing: 1.8px;
}

.brand-text strong {
    display: block;
    color: #f5f0fc;
    font-size: 11px;
    font-weight: 600;
}

.main-heading {
    margin: 0 0 5px 0;
    color: #f7f5fc;
    font-size: 27px;
    font-weight: 650;
    letter-spacing: -0.8px;
}

.main-subheading {
    color: #bdb5ce;
    font-size: 12px;
}

/* Barra lateral */

[data-testid="stSidebar"] {
    background: #2d2c3b;
    border-right: 1px solid #484157;
}

[data-testid="stSidebar"] > div:first-child {
    background: #2d2c3b;
}

[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #f5f0fc;
    letter-spacing: -0.3px;
}

[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span {
    color: #c9c2d8;
}

[data-testid="stSidebar"] hr {
    border-color: #494356;
}

/* Navegación */

[data-testid="stSidebarNav"] {
    padding-top: 12px;
}

[data-testid="stSidebarNav"] a {
    border-radius: 9px;
    margin: 3px 8px;
    color: #c7c0d7;
    transition: background 0.2s ease;
}

[data-testid="stSidebarNav"] a:hover {
    background: #403b52;
    color: #ffffff;
}

[data-testid="stSidebarNav"] a[aria-current="page"] {
    background: #7560d932;
    color: #e9dfff;
    border: 1px solid #ab91ff44;
}

/* Títulos y textos */

h1, h2, h3, h4 {
    color: #f7f5fc !important;
    letter-spacing: -0.5px;
}

p, li {
    color: #d0cadc;
    line-height: 1.7;
}

[data-testid="stCaptionContainer"] {
    color: #aaa2bc;
}

/* Separadores */

hr {
    border-color: #484157;
}

/* Campos de entrada */

[data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input,
[data-testid="stDateInput"] input,
[data-testid="stTextArea"] textarea {
    background-color: #252330 !important;
    color: #f5f3fc !important;
    border: 1px solid #655a76 !important;
    border-radius: 9px !important;
}

[data-testid="stSelectbox"] [data-baseweb="select"] > div {
    background-color: #252330 !important;
    color: #f5f3fc !important;
    border-color: #655a76 !important;
    border-radius: 9px !important;
}

[data-testid="stNumberInput"] button {
    background-color: #383448 !important;
    color: #eee8fa !important;
    border-color: #65577d !important;
}

[data-testid="stFileUploader"] section {
    background-color: #302e3e !important;
    border: 1px dashed #65577d !important;
    color: #eee8fa !important;
}

[data-testid="stFileUploader"] section * {
    color: #d0c5e5 !important;
}

/* Mensajes informativos */

[data-testid="stAlert"] {
    background-color: #332e43 !important;
    border: 1px solid #65577d !important;
    border-radius: 10px !important;
}

[data-testid="stAlert"] p {
    color: #e6def4 !important;
}

/* Casillas de selección */

[data-testid="stCheckbox"] label {
    color: #e6def4 !important;
}

/* Botones */

.stButton > button,
.stDownloadButton > button {
    min-height: 42px;
    border-radius: 9px;
    padding: 8px 17px;
    background: #383448;
    color: #eee8fa;
    border: 1px solid #65577d;
    font-weight: 600;
    transition: all 0.2s ease;
}

.stButton > button:hover,
.stDownloadButton > button:hover {
    border-color: #b295f6;
    color: #ffffff;
    background: #49405d;
    transform: translateY(-1px);
}

.stButton > button[kind="primary"] {
    background: linear-gradient(110deg, #7653de, #8c568f);
    color: #ffffff;
    border: 1px solid #a78be7;
}

.stButton > button[kind="primary"]:hover {
    background: linear-gradient(110deg, #8768e8, #a16aa5);
    border-color: #d0b9ff;
}

/* Tarjetas de métricas */

[data-testid="stMetric"] {
    background: linear-gradient(145deg, #343142, #2e2c3c);
    border: 1px solid #4c455e;
    border-radius: 13px;
    padding: 16px 18px;
    box-shadow: 0 7px 20px rgba(0, 0, 0, 0.10);
}

[data-testid="stMetricLabel"] {
    color: #bdb5ce !important;
}

[data-testid="stMetricValue"] {
    color: #d5bfff !important;
    font-weight: 650;
}

/* Pestañas */

.stTabs [data-baseweb="tab-list"] {
    background: #302e3e;
    border: 1px solid #484157;
    border-radius: 11px;
    gap: 5px;
    padding: 6px;
}

.stTabs [data-baseweb="tab"] {
    color: #c7c0d7;
    border-radius: 8px;
    padding: 9px 15px;
}

.stTabs [aria-selected="true"] {
    background: #7560d932;
    color: #eee5ff !important;
}

/* Tablas */

[data-testid="stDataFrame"],
[data-testid="stDataEditor"] {
    border: 1px solid #484157;
    border-radius: 10px;
    overflow: hidden;
}

/* Mensajes */

[data-testid="stAlert"] {
    border-radius: 10px;
    border: 1px solid #615377;
}

/* Casillas */

[data-testid="stCheckbox"] label {
    color: #d9d2e6;
}

/* Gráficas */

[data-testid="stPlotlyChart"] {
    background: #2d2c3b;
    border: 1px solid #484157;
    border-radius: 12px;
    padding: 5px;
}

/* Adaptación a pantallas pequeñas */

@media (max-width: 700px) {
    [data-testid="stMainBlockContainer"] {
        padding: 1rem 1rem 2rem;
    }

    .brand-header {
        align-items: flex-start;
        flex-direction: column;
        padding: 14px;
    }

    .brand-logos {
        gap: 9px;
        padding: 6px 9px;
    }

    .brand-urosario {
        width: 125px;
        height: 40px;
    }

    .brand-macc {
        width: 82px;
        height: 34px;
    }

    .brand-text {
        text-align: left;
    }

    .main-heading {
        font-size: 23px;
    }
}

@media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
        animation: none !important;
        transition: none !important;
    }
}

/* Corrección de selectores desplegables */

[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stSelectbox"] [data-baseweb="select"] [role="combobox"] {
    background-color: #252330 !important;
    color: #f5f3fc !important;
    border-color: #655a76 !important;
    border-radius: 9px !important;
}

[data-testid="stSelectbox"] [data-baseweb="select"] * {
    color: #f5f3fc !important;
}

[data-testid="stSelectbox"] svg {
    fill: #d5bfff !important;
}

/* Menú desplegable */

[data-baseweb="popover"] [role="listbox"],
[data-baseweb="popover"] [role="option"] {
    background-color: #302e3e !important;
    color: #f5f3fc !important;
}

[data-baseweb="popover"] [role="option"]:hover {
    background-color: #49405d !important;
}

/* Mensajes informativos oscuros */

[data-testid="stAlert"],
[data-testid="stAlert"] > div {
    background-color: #332e43 !important;
    color: #e6def4 !important;
    border: 1px solid #65577d !important;
    border-radius: 10px !important;
}

[data-testid="stAlert"] p,
[data-testid="stAlert"] span {
    color: #e6def4 !important;
}

/* Evitar que se corte el texto de las casillas */

[data-testid="stCheckbox"] label {
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
}

</style>

"""


def _imagen_base64(nombre: str) -> str | None:
    """Lee un recurso gráfico y lo convierte a Base64."""
    archivo = ASSETS / nombre

    if not archivo.exists():
        return None

    contenido = base64.b64encode(archivo.read_bytes()).decode("ascii")

    extension = archivo.suffix.lower()

    if extension == ".svg":
        mime = "image/svg+xml"
    elif extension == ".png":
        mime = "image/png"
    else:
        return None

    return f"data:{mime};base64,{contenido}"


def _encabezado() -> None:
    """Muestra el encabezado institucional y el nombre del proyecto."""
    logo_ur = _imagen_base64("universidad_oficial.svg")
    logo_macc = _imagen_base64("macc.png")

    imagenes = ""

    if logo_ur:
        imagenes += (
            f'<img class="brand-urosario" '
            f'src="{logo_ur}" alt="Universidad del Rosario">'
        )

    if logo_macc:
        imagenes += (
            f'<img class="brand-macc" '
            f'src="{logo_macc}" alt="MACC">'
        )

    if not imagenes:
        imagenes = (
            '<span style="color:#252431;font-weight:700;">'
            'Universidad del Rosario · MACC</span>'
        )

    st.markdown(
        f"""
        <header class="brand-header">
            <div class="brand-logos">
                {imagenes}
            </div>
            <div class="brand-text">
                <strong>PROYECTO FINAL</strong>
                REPRESENTACIÓN Y SOLUCIÓN AUTOMÁTICA DE PROBLEMAS
            </div>
        </header>

        <div style="margin-bottom: 28px;">
            <div class="main-heading">
                Planificador académico de horarios
            </div>
            <div class="main-subheading">
                Generación, búsqueda y optimización de horarios académicos
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    """Configura la página, los estilos y la navegación."""
    st.set_page_config(
        page_title="Planificador académico de horarios",
        page_icon="📅",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(CSS, unsafe_allow_html=True)

    sesion.inicializar()
    sesion.barra_lateral()

    _encabezado()

    paginas = [
        st.Page(
            pagina_instancia.render,
            title="Instancia",
            url_path="instancia",
            default=True,
        ),
        st.Page(
            pagina_ejecutar.render,
            title="Ejecutar y animar",
            url_path="ejecutar",
        ),
        st.Page(
            pagina_comparar.render,
            title="Comparar",
            url_path="comparar",
        ),
    ]

    st.navigation(paginas).run()


main()