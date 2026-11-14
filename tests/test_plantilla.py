"""Pruebas del generador de la plantilla de entrada."""

import pytest
from openpyxl import load_workbook

from planificador.io_datos import plantilla
from planificador.io_datos.esquema import (
    HOJAS, VERSION_ESQUEMA, Columna, Hoja)


@pytest.fixture()
def ruta(tmp_path):
    return plantilla.generar_plantilla(tmp_path / "p.xlsx")


def test_hojas_y_encabezados(ruta):
    wb = load_workbook(ruta)
    assert wb.sheetnames == ["LEEME"] + [h.nombre for h in HOJAS]
    enc = plantilla.leer_encabezados(ruta)
    assert list(enc) == [h.nombre for h in HOJAS]
    for h in HOJAS:
        assert enc[h.nombre] == [c.nombre for c in h.columnas]


def test_validaciones_de_opcion(ruta):
    wb = load_workbook(ruta)
    for h in HOJAS:
        ws = wb[h.nombre]
        for i, c in enumerate(h.columnas, start=1):
            if c.tipo != "opcion":
                continue
            letra = plantilla.get_column_letter(i)
            dvs = [dv for dv in ws.data_validations.dataValidation
                   if dv.type == "list"
                   and f"{letra}2:{letra}500" in str(dv.sqref)]
            assert dvs, f"{h.nombre}.{c.nombre} sin validación"
            for o in c.opciones:
                assert str(o) in dvs[0].formula1


def test_referencias_apuntan_a_otra_hoja(ruta):
    ws = load_workbook(ruta)["Modulos"]
    nombres = [c.nombre for c in HOJAS[4].columnas]
    assert "docente_id" in nombres
    formulas = [dv.formula1 for dv in ws.data_validations.dataValidation]
    assert "=Docentes!$A$2:$A$500" in formulas


def test_version_en_leeme(ruta):
    ws = load_workbook(ruta)["LEEME"]
    assert ws[plantilla.CELDA_VERSION].value == VERSION_ESQUEMA
    assert VERSION_ESQUEMA in ws["A2"].value


def test_con_y_sin_ejemplos(tmp_path):
    con = load_workbook(plantilla.generar_plantilla(tmp_path / "a.xlsx"))
    sin = load_workbook(
        plantilla.generar_plantilla(tmp_path / "b.xlsx", con_ejemplos=False))
    for h in HOJAS:
        assert any(c.value is not None for c in con[h.nombre][2])
        assert all(c.value is None for c in sin[h.nombre][2])


def test_formato_condicional_en_grilla(ruta):
    ws = load_workbook(ruta)["Disponibilidad"]
    assert len(ws.conditional_formatting) > 0


def test_esquema_falso_no_hardcodeado(tmp_path, monkeypatch):
    falsa = (
        Hoja("Cosas", "Hoja de prueba.", "Nadie", (
            Columna("codigo", "texto", True, "Código", ejemplo="X1"),
            Columna("color", "opcion", True, "Color", ("ROJO", "AZUL"),
                    ejemplo="ROJO"),
        )),
        Hoja("Otras", "Otra hoja.", "Alguien", (
            Columna("cosa", "texto", True, "Cosa", referencia="Cosas.codigo"),
            Columna("n", "entero", False, "Cantidad"),
        )),
    )
    monkeypatch.setattr(plantilla, "HOJAS", falsa)
    ruta = plantilla.generar_plantilla(tmp_path / "f.xlsx")
    wb = load_workbook(ruta)
    assert wb.sheetnames == ["LEEME", "Cosas", "Otras"]
    assert plantilla.leer_encabezados(ruta) == {
        "Cosas": ["codigo", "color"], "Otras": ["cosa", "n"]}
    formulas = [dv.formula1 for dv in wb["Otras"].data_validations
                .dataValidation]
    assert "=Cosas!$A$2:$A$500" in formulas
    textos = [c.value for fila in wb["LEEME"].iter_rows() for c in fila]
    assert "Cosas" in textos and "ROJO, AZUL" in textos


def test_parametro_hojas(tmp_path):
    h = Hoja("Solo", "d", "q", (Columna("a", "texto", True, "A"),))
    ruta = plantilla.generar_plantilla(tmp_path / "h.xlsx", hojas=(h,))
    assert plantilla.leer_encabezados(ruta) == {"Solo": ["a"]}


def test_main_crea_carpeta(tmp_path):
    destino = tmp_path / "nueva" / "x.xlsx"
    assert plantilla.main(["--salida", str(destino), "--sin-ejemplos"]) == 0
    assert destino.exists()
