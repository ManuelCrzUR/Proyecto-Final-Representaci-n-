"""Gráficas y tabla resumen de los experimentos (PNG con matplotlib).

``generar_graficas(csv, carpeta)`` produce los PNG; ``tabla_resumen(csv)``
agrega las corridas por (escenario, dificultad, n, algoritmo) y guarda CSV y
Markdown. Las barras de error son la desviación estándar muestral entre
semillas (``ddof=1``; sin barra si hay una sola semilla).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import NullFormatter  # noqa: E402

GRUPO = ["escenario", "dificultad", "n", "algoritmo"]
METRICAS = [
    "v", "F", "f", "tiempo_s",
    "nodos_expandidos", "nodos_generados",
    "longitud_solucion", "memoria_max_aprox",
    "movidos", "estabilidad"
]

COLUMNAS_TABLA = (
    GRUPO + ["corridas", "tasa_exito", "tasa_optimalidad"]
    + [f"{m}_{s}" for m in METRICAS for s in ("media", "desv")]
    + ["F_exito_media", "F_exito_desv"]
)
ETIQUETAS = {
    "tiempo_s": "Tiempo de ejecución (s)", "n": "Número de bloques (n)",
    "nodos_expandidos": "Nodos expandidos", "exito": "Tasa de éxito (v = 0)",
    "F": "Costo F (solo corridas exitosas)", "estabilidad": "Estabilidad",
    "movidos": "Bloques movidos" , "nodos_generados": "Nodos generados",
    "longitud_solucion": "Bloques ubicados",
    "memoria_max_aprox": "Memoria máxima aproximada",}
NOMBRE_ESC = {"construccion": "Construcción", "reparacion": "Reparación"}


def _leer(csv) -> pd.DataFrame:
    df = pd.read_csv(csv)
    df["exito"] = df["exito"].astype(bool)
    return df


def _colores(algoritmos) -> dict:
    ciclo = plt.get_cmap("tab10").colors
    return {a: ciclo[i % len(ciclo)] for i, a in enumerate(sorted(algoritmos))}


def _agregar(df, x, y, por="algoritmo") -> pd.DataFrame:
    """Media y desviación de ``y`` por (``por``, ``x``)."""
    g = df.groupby([por, x])[y].agg(["mean", "std", "count"]).reset_index()
    g["std"] = g["std"].fillna(0.0)
    return g


def _lineas(ax, df, x, y, colores, log_y=False, por="algoritmo"):
    """Dibuja una línea con barras de error por cada valor de ``por``."""
    hay = False
    for clave, sub in _agregar(df.dropna(subset=[y]), x, y, por).groupby(por):
        sub = sub.sort_values(x)
        err = sub["std"]
        if y in("exito", "estabilidad"):  # una proporción no sale de [0, 1]
            err = [sub["std"].clip(upper=sub["mean"]),
                   sub["std"].clip(upper=1 - sub["mean"])]
        ax.errorbar(sub[x], sub["mean"], yerr=err, marker="o",
                    capsize=3, label=str(clave),
                    color=colores.get(clave), linewidth=1.5)
        hay = True
    if log_y and hay:
        ax.set_yscale("log")
    if y in ("exito", "estabilidad"):
        ax.set_ylim(0, 1)    
    ax.set_xlabel(ETIQUETAS.get(x, x))
    ax.set_ylabel(ETIQUETAS.get(y, y) + (" (escala log)" if log_y else ""))
    ax.grid(alpha=0.3)
    return hay


def _panel(df, y, titulo, archivo, carpeta, colores, filas="escenario",
           cols="dificultad", x="n", log_y=False) -> Optional[Path]:
    """Figura con una malla filas x cols de líneas ``y`` vs ``x``."""
    if df.empty:
        return None
    valores_f = sorted(df[filas].unique())
    valores_c = sorted(df[cols].unique())
    fig, ejes = plt.subplots(len(valores_f), len(valores_c), squeeze=False,
                             figsize=(5.2 * len(valores_c),
                                      3.8 * len(valores_f)))
    alguno = False
    for i, vf in enumerate(valores_f):
        for j, vc in enumerate(valores_c):
            ax = ejes[i][j]
            sub = df[(df[filas] == vf) & (df[cols] == vc)]
            if not _lineas(ax, sub, x, y, colores, log_y):
                ax.text(0.5, 0.5, "sin datos", ha="center",
                        transform=ax.transAxes)
            else:
                alguno = True
                if x == "n":
                    ax.set_xscale("log")
                    ax.set_xticks(sorted(sub["n"].unique()))
                    ax.set_xticklabels(sorted(sub["n"].unique()))
                    ax.xaxis.set_minor_formatter(NullFormatter())
            ax.set_title(f"{NOMBRE_ESC.get(vf, vf)} - {vc}")
    if not alguno:
        plt.close(fig)
        return None
    h, e = [], []
    for ax in ejes.ravel():
        for hh, ee in zip(*ax.get_legend_handles_labels()):
            if ee not in e:
                h.append(hh)
                e.append(ee)
    fig.legend(h, e, title="Algoritmo", loc="center left",
               bbox_to_anchor=(1.0, 0.5))
    fig.suptitle(titulo)
    fig.tight_layout()
    ruta = Path(carpeta) / archivo
    fig.savefig(ruta, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return ruta


def _ancho(df) -> pd.DataFrame:
    """Filas de beam con columna ``ancho`` extraída de ``parametros``."""
    b = df[df["algoritmo"].str.startswith("beam")].copy()
    b["ancho"] = b["parametros"].map(
        lambda s: json.loads(s).get("ancho") if isinstance(s, str) else None)
    return b.dropna(subset=["ancho"])


def _grafica_beam(df, carpeta) -> list:
    """F y tiempo vs ancho del haz (solo si hay barrido de ancho)."""
    b = _ancho(df[df["escenario"] == "construccion"])
    if b["ancho"].nunique() < 3:
        return []
    b["serie"] = b["dificultad"] + ", n=" + b["n"].astype(str)
    b["ancho"] = b["ancho"].astype(int)
    salidas = []
    series = sorted(b["serie"].unique())
    cmap = {s: plt.get_cmap("tab10").colors[i % 10]
            for i, s in enumerate(series)}
    paneles = [("F", "Calidad F vs ancho del haz (corridas exitosas)",
                "beam_F_vs_ancho.png", False, True),
               ("tiempo_s", "Tiempo vs ancho del haz",
                "beam_tiempo_vs_ancho.png", True, False),
               ("exito", "Tasa de éxito vs ancho del haz",
                "beam_exito_vs_ancho.png", False, False)]
    for y, titulo, archivo, log_y, solo_exito in paneles:
        d = b[b["exito"]] if solo_exito else b
        if d.empty:
            continue
        d = d.assign(exito=d["exito"].astype(float))
        fig, ax = plt.subplots(figsize=(6.5, 4.2))
        _lineas(ax, d, "ancho", y, cmap, log_y, por="serie")
        ax.set_xscale("log")
        ax.set_xticks(sorted(d["ancho"].unique()))
        ax.set_xticklabels(sorted(d["ancho"].unique()))
        ax.xaxis.set_minor_formatter(NullFormatter())
        ax.set_xlabel("Ancho del haz k (escala log)")
        ax.set_ylabel(ETIQUETAS.get(y, y))
        ax.set_title(titulo)
        ax.legend(title="Dificultad, tamaño")
        fig.tight_layout()
        ruta = Path(carpeta) / archivo
        fig.savefig(ruta, dpi=130)
        plt.close(fig)
        salidas.append(ruta)
    return salidas


def generar_graficas(csv, carpeta) -> list:
    """Genera los PNG a partir de ``csv`` en ``carpeta``; devuelve rutas."""
    df = _leer(csv)
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    colores = _colores(df["algoritmo"].unique())
    cons = df[df["escenario"] == "construccion"]
    rep = df[df["escenario"] == "reparacion"]
    ex = df.assign(exito=df["exito"].astype(float))
    exitosos = df[df["exito"]]
    rutas = [
        _panel(cons, "tiempo_s", "Tiempo vs tamaño (construcción)",
               "tiempo_vs_n.png", carpeta, colores, log_y=True),
        _panel(ex, "exito", "Tasa de éxito vs tamaño",
               "exito_vs_n.png", carpeta, colores),
        _panel(cons, "nodos_expandidos",
               "Nodos expandidos vs tamaño (construcción)",
               "nodos_vs_n.png", carpeta, colores, log_y=True),
        _panel(cons, "nodos_generados",
               "Nodos generados vs tamaño (construcción)",
               "nodos_generados_vs_n.png",
               carpeta, colores, log_y=True),
        _panel(df, "longitud_solucion",
               "Bloques ubicados vs tamaño",
               "longitud_solucion_vs_n.png",
               carpeta, colores),
        _panel(exitosos, "F", "Costo F vs tamaño (solo corridas exitosas)",
               "F_vs_n.png", carpeta, colores),
        _panel(rep, "estabilidad", "Reparación: estabilidad vs tamaño",
               "reparacion_estabilidad.png", carpeta, colores),
        _panel(rep, "movidos", "Reparación: bloques movidos vs tamaño",
               "reparacion_movidos.png", carpeta, colores),
    ]
    rutas += _grafica_beam(df, carpeta)
    return [r for r in rutas if r is not None]


def _fmt(media, desv, dec=2) -> str:
    if pd.isna(media):
        return "-"
    return f"{media:.{dec}f} ± {0.0 if pd.isna(desv) else desv:.{dec}f}"


def tabla_resumen(csv, salida=None) -> pd.DataFrame:
    """Agrega por escenario, dificultad, n y algoritmo (media y desviación).

    Si se indica ``salida`` guarda ``tabla_resumen.csv`` y
    ``tabla_resumen.md`` (media ± desv., lista para el informe).
    """
    df = _leer(csv)
    filas = []
    for clave, sub in df.groupby(GRUPO, sort=True):
        fila = dict(zip(GRUPO, clave))
        fila["corridas"] = len(sub)
        fila["tasa_exito"] = float(sub["exito"].mean())
        fila["tasa_optimalidad"] = float(sub["optimo_demostrado"].astype(bool).mean())
        for m in METRICAS:
            fila[f"{m}_media"] = sub[m].mean()
            fila[f"{m}_desv"] = sub[m].std(ddof=1) if sub[m].count() > 1 \
                else (0.0 if sub[m].count() else float("nan"))
        ok = sub[sub["exito"]]["F"]
        fila["F_exito_media"] = ok.mean() if len(ok) else float("nan")
        fila["F_exito_desv"] = (ok.std(ddof=1) if len(ok) > 1
                                else (0.0 if len(ok) else float("nan")))
        filas.append(fila)
    tabla = pd.DataFrame(filas, columns=COLUMNAS_TABLA)
    if salida is not None:
        salida = Path(salida)
        salida.mkdir(parents=True, exist_ok=True)
        tabla.to_csv(salida / "tabla_resumen.csv", index=False)
        (salida / "tabla_resumen.md").write_text(_markdown(tabla),
                                                 encoding="utf-8")
    return tabla


def _markdown(tabla: pd.DataFrame) -> str:
    """Genera tablas Markdown completas para el informe."""
    partes = []

    cab = [
        "Dificultad", "Bloques", "Algoritmo", "Corridas",
        "Éxito", "Optimalidad", "Costo F (exitosos)",
        "Violaciones", "Tiempo (s)", "Nodos exp.",
        "Nodos gen.", "Bloques asignados", "Memoria aprox."
    ]

    for esc, sub in tabla.groupby("escenario"):
        es_reparacion = esc == "reparacion"

        columnas = cab.copy()
        if es_reparacion:
            columnas += ["Bloques movidos", "Estabilidad"]

        partes.append(f"### {NOMBRE_ESC.get(esc, esc)}\n")
        partes.append("| " + " | ".join(columnas) + " |")
        partes.append("|" + "---|" * len(columnas))

        for _, r in sub.iterrows():
            valores = [
                r["dificultad"],
                str(r["n"]),
                r["algoritmo"],
                str(r["corridas"]),
                f"{100 * r['tasa_exito']:.0f} %",
                f"{100 * r['tasa_optimalidad']:.0f} %",
                _fmt(r["F_exito_media"], r["F_exito_desv"], 2),
                _fmt(r["v_media"], r["v_desv"], 1),
                _fmt(r["tiempo_s_media"], r["tiempo_s_desv"], 3),
                _fmt(r["nodos_expandidos_media"],
                     r["nodos_expandidos_desv"], 0),
                _fmt(r["nodos_generados_media"],
                     r["nodos_generados_desv"], 0),
                _fmt(r["longitud_solucion_media"],
                     r["longitud_solucion_desv"], 1),
                _fmt(r["memoria_max_aprox_media"],
                     r["memoria_max_aprox_desv"], 1),
            ]

            if es_reparacion:
                valores += [
                    _fmt(r["movidos_media"], r["movidos_desv"], 1),
                    _fmt(r["estabilidad_media"],
                         r["estabilidad_desv"], 2)
                ]

            partes.append("| " + " | ".join(valores) + " |")

        partes.append("")

    partes.append(
        "**Nota:** La memoria es una aproximación basada en estructuras "
        "diferentes según el algoritmo; no representa bytes directamente "
        "comparables. La optimalidad corresponde a la garantía demostrada "
        "por cada ejecución."
    )

    return "\n".join(partes)


def main(argv=None) -> int:
    """CLI: genera gráficas y tabla resumen desde un CSV de resultados."""
    ap = argparse.ArgumentParser(description="Gráficas de experimentos")
    ap.add_argument("--csv", required=True)
    ap.add_argument("--salida", default=None)
    args = ap.parse_args(argv)
    salida = Path(args.salida) if args.salida else Path(args.csv).parent
    rutas = generar_graficas(args.csv, salida)
    tabla_resumen(args.csv, salida)
    for r in rutas:
        print(r)
    print(salida / "tabla_resumen.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
