"""Figuras de Plotly de la interfaz (módulo puro, sin Streamlit)."""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def figura_proceso(cuadros: list, idx: int) -> go.Figure:
    """F, v y tamaño de frontera por paso, con marcador en el cuadro ``idx``.

    El eje x es el ``paso`` del evento; solo se dibujan los eventos que
    traen el valor correspondiente.
    """
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=0.12,
                        subplot_titles=("F (línea) y v (puntos)",
                                        "Tamaño de la frontera"))
    pasos_f = [(c.evento.paso, c.evento.F) for c in cuadros
               if c.evento.F is not None]
    pasos_v = [(c.evento.paso, c.evento.v) for c in cuadros
               if c.evento.v is not None]
    pasos_t = [(c.evento.paso, c.evento.tam_frontera) for c in cuadros
               if c.evento.tam_frontera is not None]
    if pasos_f:
        fig.add_trace(go.Scatter(
            x=[p for p, _ in pasos_f], y=[y for _, y in pasos_f],
            mode="lines", name="F", line={"color": "#1f77b4"}), 1, 1)
    if pasos_v:
        fig.add_trace(go.Scatter(
            x=[p for p, _ in pasos_v], y=[y for _, y in pasos_v],
            mode="markers", name="v", marker={"color": "#d62728",
                                              "size": 5}), 1, 1)
    if pasos_t:
        fig.add_trace(go.Scatter(
            x=[p for p, _ in pasos_t], y=[y for _, y in pasos_t],
            mode="lines", name="frontera", line={"color": "#2ca02c"}), 2, 1)
    if cuadros:
        paso = cuadros[max(0, min(idx, len(cuadros) - 1))].evento.paso
        fig.add_vline(x=paso, line_dash="dash", line_color="#444")
    fig.update_xaxes(title_text="paso de la traza", row=2, col=1)
    fig.update_layout(height=340, margin={"l": 40, "r": 10, "t": 30, "b": 30},
                      legend={"orientation": "h", "y": 1.12})
    if not (pasos_f or pasos_v or pasos_t):
        fig.add_annotation(text="La traza no trae F, v ni frontera",
                           showarrow=False)
    return fig


def figura_barras(df: pd.DataFrame, columna: str, titulo: str,
                  log: bool = False) -> go.Figure:
    """Barras por algoritmo de ``columna`` (``df`` con columna ``algoritmo``)."""
    fig = go.Figure(go.Bar(x=df["algoritmo"], y=df[columna],
                           marker_color="#1f77b4"))
    fig.update_layout(title=titulo, height=300,
                      margin={"l": 40, "r": 10, "t": 40, "b": 30})
    if log:
        fig.update_yaxes(type="log")
    return fig


def red_conflictos(conflictos: dict, max_nodos: int = 80) -> go.Figure:
    """Grafo Γ en disposición circular (solo si es pequeño)."""
    ids = sorted(conflictos)[:max_nodos]
    pos = {b: (math.cos(2 * math.pi * i / max(1, len(ids))),
               math.sin(2 * math.pi * i / max(1, len(ids))))
           for i, b in enumerate(ids)}
    xs, ys = [], []
    for u in ids:
        for v in conflictos[u]:
            if v in pos and u < v:
                xs += [pos[u][0], pos[v][0], None]
                ys += [pos[u][1], pos[v][1], None]
    fig = go.Figure([
        go.Scatter(x=xs, y=ys, mode="lines",
                   line={"width": 0.6, "color": "#999"}, hoverinfo="skip"),
        go.Scatter(x=[pos[b][0] for b in ids], y=[pos[b][1] for b in ids],
                   mode="markers+text", text=ids, textposition="top center",
                   marker={"size": 9, "color": "#1f77b4"},
                   hovertext=[f"{b}: grado {len(conflictos[b])}"
                              for b in ids])])
    fig.update_layout(height=420, showlegend=False,
                      margin={"l": 10, "r": 10, "t": 10, "b": 10},
                      xaxis={"visible": False}, yaxis={"visible": False})
    return fig
