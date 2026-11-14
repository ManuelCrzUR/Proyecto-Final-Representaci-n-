"""Pruebas de la herramienta de auditoría de horas."""

import importlib.util
from pathlib import Path

import openpyxl
import pytest

RAIZ = Path(__file__).resolve().parent.parent
RUTA_MODULO = RAIZ / "herramientas" / "auditoria_horas.py"

_spec = importlib.util.spec_from_file_location("auditoria_horas", RUTA_MODULO)
aud = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(aud)


def _horas(inicio, fin):
    return (fin - inicio) / 60


def test_franja_simple():
    ini, fin, avisos = aud.parsear_franja("7:00 A 8:00 AM")
    assert (ini, fin) == (7 * 60, 8 * 60)
    assert avisos == []


def test_franja_am_erroneo_se_corrige_a_pm():
    ini, fin, avisos = aud.parsear_franja("11:20 A 12:20 AM")
    assert _horas(ini, fin) == 1
    assert fin == 12 * 60 + 20
    assert len(avisos) == 1
    assert "AM" in avisos[0] and "PM" in avisos[0]


def test_franja_receso_son_20_minutos():
    ini, fin, avisos = aud.parsear_franja("10:00 A 10:20 AM")
    assert fin - ini == 20
    assert avisos == []


def test_franja_larga_de_manana():
    ini, fin, avisos = aud.parsear_franja("7:00 A 12:20 PM")
    assert (ini, fin) == (7 * 60, 12 * 60 + 20)
    assert avisos == []


def test_franja_mediodia_con_am_erroneo():
    ini, fin, avisos = aud.parsear_franja("12:20 A 1:20 AM")
    assert (ini, fin) == (12 * 60 + 20, 13 * 60 + 20)
    assert avisos


def test_franja_con_ceros_a_la_izquierda():
    ini, fin, _ = aud.parsear_franja("03:30 A 05:00 PM")
    assert _horas(ini, fin) == 1.5


def test_franja_ilegible():
    ini, fin, avisos = aud.parsear_franja("PRACTICA")
    assert ini is None and fin is None and avisos


def test_franjas_practica_dos_rangos():
    rangos, avisos = aud.parsear_franjas(
        "PRACTICA:\n8:00 A 12:00 Y 2:00 A 5:00 PM")
    assert rangos == [(8 * 60, 12 * 60), (14 * 60, 17 * 60)]
    assert avisos == []


def test_franjas_con_pm_explicito_en_ambos():
    rangos, _ = aud.parsear_franjas("2:00 PM A 6:00 PM")
    assert rangos == [(14 * 60, 18 * 60)]


def test_normalizar_basico():
    assert aud.normalizar("  Ética   y\nValores ") == "ETICA Y VALORES"


def test_normalizar_quita_docente_y_parentesis_desbalanceado():
    assert aud.normalizar("DERECHO PENAL\n(Juan Pérez)") == "DERECHO PENAL"
    assert aud.normalizar("BALISTICA (Ana") == "BALISTICA"
    asignatura, docente = aud.separar_docente("BALISTICA (Ana")
    assert asignatura == "BALISTICA" and docente == "Ana"


def test_normalizar_conserva_parentesis_si_se_pide():
    assert "CRIMINALISTICA" in aud.normalizar(
        "INVESTIGACION (CRIMINALISTICA)", quitar_docente=False)


def test_emparejar_exacta_difusa_y_sin_emparejar():
    malla = ["ÉTICA Y VALORES", "DERECHO PROCESAL PENAL",
             "SOPORTE VITAL", "BALISTICA"]
    cal = ["ETICA Y VALORES", "DERECHOS PROCESAL PENAL",
           "SOPORTE VITAL BASICO", "PLAN DE ACOGIDA"]
    emp = aud.emparejar(cal, malla).set_index("calendario")
    assert emp.loc["ETICA Y VALORES", "metodo"] == "exacta"
    assert emp.loc["ETICA Y VALORES", "puntaje"] == 1.0
    assert emp.loc["DERECHOS PROCESAL PENAL", "metodo"] == "difusa"
    assert emp.loc["DERECHOS PROCESAL PENAL", "puntaje"] >= 0.8
    assert emp.loc["SOPORTE VITAL BASICO", "metodo"] == "contiene"
    assert emp.loc["SOPORTE VITAL BASICO", "modulo"] == "SOPORTE VITAL"
    assert emp.loc["PLAN DE ACOGIDA", "modulo"] == aud.SIN_EMPAREJAR


def test_emparejar_ambigua_no_se_inventa():
    malla = ["DERECHO PENAL GENERAL", "DERECHO PENAL ESPECIAL"]
    emp = aud.emparejar(["DERECHO PENAL"], malla)
    assert emp.iloc[0]["modulo"] == aud.SIN_EMPAREJAR


def _hay_datos():
    return (aud.MALLA_DEFECTO.exists()
            and aud.CALENDARIO_DEFECTO.exists())


@pytest.mark.integracion
@pytest.mark.filterwarnings(
    "ignore::pytest.PytestUnknownMarkWarning")
def test_integracion_reporte_completo(tmp_path):
    if not _hay_datos():
        pytest.skip("No están los Excel reales en 'data exp/'")
    resultados = aud.auditar(aud.MALLA_DEFECTO, aud.CALENDARIO_DEFECTO)
    salida = tmp_path / "salidas" / "auditoria_horas.xlsx"
    ruta = aud.generar_reporte(resultados, salida)
    assert ruta.exists()
    libro = openpyxl.load_workbook(ruta)
    for hoja in ("Resumen", "Por modulo", "Sin emparejar", "Advertencias",
                 "Metodologia"):
        assert hoja in libro.sheetnames
    malla = resultados["malla"]
    assert 30 <= len(malla) <= 40
    assert resultados["totales_malla"]["teoria"] > 0
    datos = resultados["hojas"]["INV.JUD 2026-1"]
    ses = datos["sesiones"]
    assert ses[ses["tipo"].isin(aud.TIPOS_HORAS)]["horas"].sum() > 0
