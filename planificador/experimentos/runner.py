"""Ejecutor de experimentos reproducibles.

Dada una configuración JSON, recorre la malla escenario x dificultad x
tamaño x semilla x algoritmo y escribe una fila por corrida en
``resultados.csv``, junto con ``metadata.json`` (configuración, versiones y
fecha). Todo es determinista salvo las columnas de tiempo.

Escenarios:

* ``construccion``: ``solver.resolver(instancia)`` desde un horario vacío.
* ``reparacion``: se perturba la disponibilidad de la instancia a partir de
  su solución oculta y se repara esa solución con ``reparar``.

Formato de la configuración (JSON)::

    {"nombre": "base", "semillas": [0, 1], "tamanos": [20, 50],
     "dificultades": {"holgada": {}, "ajustada": {"prob_disponible": 0.2}},
     "escenarios": ["construccion", "reparacion"],
     "algoritmos": [{"nombre": "beam", "parametros": {"ancho": 5},
                     "max_n": 100, "etiqueta": "beam_k5"}],
     "limites": {"max_segundos": 30, "max_nodos": 200000},
     "perturbacion": {"num_docentes": 1, "fraccion": 0.5}}
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime
from importlib import metadata as _md
from pathlib import Path
from typing import Optional

import pandas as pd

from planificador.algoritmos.base import Limites
from planificador.algoritmos.registro import crear_solver
from planificador.algoritmos.reparacion import reparar
from planificador.core.validador import validar
from planificador.io_datos.sintetico import (
    generar_instancia, perturbar_disponibilidad)

RAIZ = Path(__file__).resolve().parents[2]
SALIDA_BASE = RAIZ / "salidas" / "experimentos"

COLUMNAS = [
    "config", "escenario", "dificultad", "n", "semilla", "algoritmo",
    "parametros", "exito", "v", "v_sin_ubicar", "v_disp", "v_vent",
    "v_conf", "f", "F", "tiempo_s", "nodos_expandidos", "nodos_generados",
    "longitud_solucion", "bloques_totales",
    "memoria_max_aprox", "tipo_memoria",
    "max_frontera", "max_haz", "max_candidatos",
    "max_estructura", "profundidad_max",
    "optimo_demostrado", "criterio_optimalidad",
    "terminado_por", "saltados", "invalidos", "liberados", "movidos",
    "estabilidad", "v_validador", "inconsistente", "eventos_traza",
]
# Columnas que dependen del reloj (se excluyen al comparar corridas).
COLUMNAS_TIEMPO = ["tiempo_s"]
# terminado_por puede depender del reloj si una corrida roza el límite.
LIMITES_POR_DEFECTO = {"max_segundos": 30.0, "max_nodos": 200_000}


def cargar_config(ruta) -> dict:
    """Lee y valida una configuración JSON."""
    cfg = json.loads(Path(ruta).read_text(encoding="utf-8"))
    for clave in ("nombre", "semillas", "tamanos", "dificultades",
                  "escenarios", "algoritmos"):
        if clave not in cfg:
            raise ValueError(f"Falta la clave '{clave}' en la configuración")
    for e in cfg["escenarios"]:
        if e not in ("construccion", "reparacion"):
            raise ValueError(f"Escenario desconocido: {e}")
    return cfg


def reducir_config(cfg: dict) -> dict:
    """Subconjunto mínimo de ``cfg`` (modo ``--rapido``)."""
    nuevo = dict(cfg)
    nuevo["semillas"] = list(cfg["semillas"][:1])
    nuevo["tamanos"] = list(cfg["tamanos"][:1])
    nuevo["nombre"] = cfg["nombre"]
    return nuevo


def _limites(cfg: dict) -> Limites:
    lim = {**LIMITES_POR_DEFECTO, **cfg.get("limites", {})}
    return Limites(max_nodos=lim["max_nodos"],
                   max_segundos=lim["max_segundos"])


def _versiones() -> dict:
    versiones = {"python": platform.python_version(),
                 "plataforma": platform.platform()}
    for paq in ("pandas", "numpy", "matplotlib", "plotly"):
        try:
            versiones[paq] = _md.version(paq)
        except _md.PackageNotFoundError:
            pass
    return versiones


def _n_saltados(extra: dict) -> int:
    s = extra.get("saltados", 0)
    try:
        return len(s)
    except TypeError:
        return int(s or 0)


def _fila(cfg, escenario, dificultad, n, semilla, alg, inst, res) -> dict:
    """Arma la fila de resultados y registra las métricas de búsqueda."""
    viol = res.violaciones
    rep = validar(inst, res.asignacion)
    v_val = rep.violaciones.total
    extra = res.extra
    parametros = alg.get("parametros", {})
    nombre = alg["nombre"]
    rep_fila = escenario == "reparacion"

    # Longitud de la solución.
    longitud = len(res.asignacion)
    bloques_totales = len(inst.bloque)

    # Métricas específicas de cada algoritmo.
    max_frontera = extra.get("max_frontera")
    max_haz = extra.get("max_haz")
    max_candidatos = extra.get("max_candidatos")
    max_estructura = extra.get("max_estructura")
    profundidad_max = extra.get("profundidad_max")

    # Memoria aproximada según la estructura utilizada.
    if nombre in ("a_estrella", "avara"):
        memoria = max_frontera
        tipo_memoria = "nodos_en_frontera"
    elif nombre == "beam":
        memoria = max_estructura
        tipo_memoria = "haz_y_candidatos"
    elif nombre == "backtracking":
        memoria = profundidad_max
        tipo_memoria = "profundidad_recursion"
    else:
        memoria = None
        tipo_memoria = "no_disponible"

    # Determinar si se demostró optimalidad respecto al costo total F.
    optimo = False
    criterio = "No garantiza optimalidad"

    if nombre == "backtracking":
        if parametros.get("modo", "primera") == "optimizar":
            if res.terminado_por == "agotado":
                optimo = bool(res.exito)
                criterio = (
                    "Costo F: branch and bound agotado"
                    if res.exito else
                    "No se encontró solución factible"
                )
            else:
                criterio = (
                    f"No demostrado: {res.terminado_por}"
                )
        else:
            criterio = "Primera solución: no garantiza F mínimo"

    elif nombre == "a_estrella":
        if parametros.get("peso_h", 1.0) == 1.0:
            criterio = "Óptimo respecto a g, no necesariamente a F"
        else:
            criterio = "A* ponderado: no garantiza optimalidad"

    elif nombre == "avara":
        criterio = "Heurística no admisible"

    elif nombre == "beam":
        criterio = "Ancho limitado: no garantiza optimalidad"
        # La reparación por vecindad no demuestra optimalidad global.
    if rep_fila:
        optimo = False
        criterio = (
            "Reparación por vecindad: no demuestra optimalidad global"
        )

    return {
        "config": cfg["nombre"],
        "escenario": escenario,
        "dificultad": dificultad,
        "n": n,
        "semilla": semilla,
        "algoritmo": alg.get("etiqueta") or nombre,
        "parametros": json.dumps(parametros, sort_keys=True),
        "exito": bool(res.exito),
        "v": viol.total,
        "v_sin_ubicar": viol.sin_ubicar,
        "v_disp": viol.disponibilidad,
        "v_vent": viol.ventana,
        "v_conf": viol.conflicto,
        "f": res.f,
        "F": res.F,
        "tiempo_s": res.tiempo_s,
        "nodos_expandidos": res.nodos_expandidos,
        "nodos_generados": res.nodos_generados,
        "longitud_solucion": longitud,
        "bloques_totales": bloques_totales,
        "memoria_max_aprox": memoria,
        "tipo_memoria": tipo_memoria,
        "max_frontera": max_frontera,
        "max_haz": max_haz,
        "max_candidatos": max_candidatos,
        "max_estructura": max_estructura,
        "profundidad_max": profundidad_max,
        "optimo_demostrado": optimo,
        "criterio_optimalidad": criterio,
        "terminado_por": res.terminado_por,
        "saltados": _n_saltados(extra),
        "invalidos": extra.get("invalidos") if rep_fila else None,
        "liberados": extra.get("liberados") if rep_fila else None,
        "movidos": extra.get("movidos") if rep_fila else None,
        "estabilidad": extra.get("estabilidad") if rep_fila else None,
        "v_validador": v_val,
        "inconsistente": v_val != viol.total,
        "eventos_traza": len(res.traza),
    }


def ejecutar(cfg: dict, salida: Optional[Path] = None,
             verbose: bool = True) -> pd.DataFrame:
    """Ejecuta ``cfg`` y guarda ``resultados.csv`` y ``metadata.json``.

    Devuelve el DataFrame de resultados. ``salida`` por defecto es
    ``salidas/experimentos/<nombre>/``.
    """
    salida = Path(salida) if salida else SALIDA_BASE / cfg["nombre"]
    salida.mkdir(parents=True, exist_ok=True)
    limites = _limites(cfg)
    pert = {"num_docentes": 1, "fraccion": 0.5, **cfg.get("perturbacion", {})}
    inicio = datetime.now()
    filas: list = []
    total = (len(cfg["escenarios"]) * len(cfg["dificultades"])
             * len(cfg["tamanos"]) * len(cfg["semillas"]))
    hecho = 0
    cache: dict = {}
    for escenario in cfg["escenarios"]:
        for dif, kwargs in cfg["dificultades"].items():
            for n in cfg["tamanos"]:
                for semilla in cfg["semillas"]:
                    hecho += 1
                    clave = (dif, n, semilla)
                    if clave not in cache:
                        cache = {clave: generar_instancia(
                            n, semilla, **kwargs)}
                    inst, sol = cache[clave]
                    inst2 = None
                    if escenario == "reparacion":
                        inst2 = perturbar_disponibilidad(
                            inst, sol, semilla, **pert)
                    for alg in cfg["algoritmos"]:
                        if n > alg.get("max_n", float("inf")):
                            continue
                        solver = crear_solver(
                            alg["nombre"], **alg.get("parametros", {}))
                        if escenario == "construccion":
                            res = solver.resolver(inst, limites=limites)
                            inst_eval = inst
                        else:
                            res = reparar(inst2, sol, solver, limites)
                            inst_eval = inst2
                        fila = _fila(cfg, escenario, dif, n, semilla, alg,
                                     inst_eval, res)
                        if fila["inconsistente"]:
                            print(f"ADVERTENCIA: v={fila['v']} != "
                                  f"validador={fila['v_validador']} en "
                                  f"{escenario}/{dif}/n={n}/s={semilla}/"
                                  f"{fila['algoritmo']}", file=sys.stderr)
                        filas.append(fila)
                    if verbose:
                        print(f"[{hecho}/{total}] {escenario} {dif} n={n} "
                              f"semilla={semilla} "
                              f"({(datetime.now() - inicio).seconds}s)",
                              flush=True)
    df = pd.DataFrame(filas, columns=COLUMNAS)
    df.to_csv(salida / "resultados.csv", index=False)
    meta = {"config": cfg, "versiones": _versiones(),
            "fecha_inicio": inicio.isoformat(timespec="seconds"),
            "duracion_s": round((datetime.now() - inicio).total_seconds(), 1),
            "filas": len(df),
            "inconsistentes": int(df["inconsistente"].sum())}
    (salida / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if verbose:
        print(f"Listo: {len(df)} filas en {salida}")
    return df


def main(argv=None) -> int:
    """CLI del runner."""
    ap = argparse.ArgumentParser(description="Ejecuta una configuración")
    ap.add_argument("--config", required=True)
    ap.add_argument("--salida", default=None)
    ap.add_argument("--rapido", action="store_true",
                    help="subconjunto mínimo (1 semilla, 1 tamaño)")
    args = ap.parse_args(argv)
    cfg = cargar_config(args.config)
    if args.rapido:
        cfg = reducir_config(cfg)
    ejecutar(cfg, args.salida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
