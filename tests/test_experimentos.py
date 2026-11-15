"""Tests del runner y las gráficas de experimentos (solo en tmp_path)."""

import json

import pandas as pd
import pytest

from planificador.experimentos import graficas, runner

CONFIG = {
    "nombre": "mini",
    "semillas": [0, 1],
    "tamanos": [8, 10],
    "dificultades": {"holgada": {}, "ajustada": {
        "prob_disponible": 0.3, "prob_ventana": 0.5}},
    "escenarios": ["construccion", "reparacion"],
    "algoritmos": [
        {"nombre": "backtracking", "parametros": {"modo": "primera"},
         "etiqueta": "backtracking"},
        {"nombre": "beam", "parametros": {"ancho": 3}, "etiqueta": "beam_k3",
         "max_n": 8},
    ],
    "limites": {"max_segundos": 5, "max_nodos": 2000},
    "perturbacion": {"num_docentes": 1, "fraccion": 0.3},
}


@pytest.fixture(scope="module")
def corrida(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("exp")
    df = runner.ejecutar(CONFIG, carpeta / "a", verbose=False)
    df2 = runner.ejecutar(CONFIG, carpeta / "b", verbose=False)
    return carpeta, df, df2


def test_columnas_y_filas(corrida):
    carpeta, df, _ = corrida
    assert list(df.columns) == runner.COLUMNAS
    # beam solo en n=8: (2 esc x 2 dif x 2 sem) x (bt en 2 n + beam en n=8)
    assert len(df) == 2 * 2 * 2 * (2 + 1)
    assert (carpeta / "a" / "resultados.csv").stat().st_size > 0
    leido = pd.read_csv(carpeta / "a" / "resultados.csv")
    assert len(leido) == len(df)


def test_max_n_se_respeta(corrida):
    _, df, _ = corrida
    assert df[df["algoritmo"] == "beam_k3"]["n"].max() <= 8
    assert (df["algoritmo"] == "backtracking").sum() == 16


def test_v_coincide_con_validador(corrida):
    _, df, _ = corrida
    assert (df["v"] == df["v_validador"]).all()
    assert not df["inconsistente"].any()


def test_reparacion_tiene_estabilidad(corrida):
    _, df, _ = corrida
    rep = df[df["escenario"] == "reparacion"]
    con = df[df["escenario"] == "construccion"]
    assert rep["estabilidad"].between(0, 1).all()
    assert con["estabilidad"].isna().all()


def test_reproducible_salvo_tiempos(corrida):
    _, df, df2 = corrida
    quitar = runner.COLUMNAS_TIEMPO
    pd.testing.assert_frame_equal(df.drop(columns=quitar),
                                  df2.drop(columns=quitar))


def test_metadata(corrida):
    carpeta, df, _ = corrida
    meta = json.loads((carpeta / "a" / "metadata.json").read_text("utf-8"))
    assert meta["config"]["nombre"] == "mini"
    assert "python" in meta["versiones"]
    assert meta["filas"] == len(df)
    assert meta["fecha_inicio"]


def test_graficas_y_tabla(corrida):
    carpeta, _, _ = corrida
    csv = carpeta / "a" / "resultados.csv"
    rutas = graficas.generar_graficas(csv, carpeta / "g")
    assert len(rutas) >= 5
    for r in rutas:
        assert r.suffix == ".png" and r.stat().st_size > 0
    tabla = graficas.tabla_resumen(csv, carpeta / "g")
    assert list(tabla.columns) == graficas.COLUMNAS_TABLA
    assert tabla["corridas"].sum() == 24
    assert (carpeta / "g" / "tabla_resumen.csv").exists()
    assert "|" in (carpeta / "g" / "tabla_resumen.md").read_text("utf-8")


def test_beam_ancho_genera_graficas(tmp_path):
    cfg = dict(CONFIG, nombre="beam_mini", tamanos=[8], semillas=[0, 1],
               escenarios=["construccion"], algoritmos=[
                   {"nombre": "beam", "parametros": {"ancho": k},
                    "etiqueta": f"beam_k{k}"} for k in (1, 2, 4)])
    df = runner.ejecutar(cfg, tmp_path, verbose=False)
    rutas = graficas.generar_graficas(tmp_path / "resultados.csv", tmp_path)
    assert any(r.name == "beam_tiempo_vs_ancho.png" for r in rutas)
    assert len(df) == 12


def test_config_invalida(tmp_path):
    ruta = tmp_path / "c.json"
    ruta.write_text(json.dumps({"nombre": "x"}), encoding="utf-8")
    with pytest.raises(ValueError):
        runner.cargar_config(ruta)


def test_reducir_config():
    red = runner.reducir_config(CONFIG)
    assert red["semillas"] == [0] and red["tamanos"] == [8]
