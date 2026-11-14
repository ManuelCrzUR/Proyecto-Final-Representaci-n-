"""Generador de la plantilla de entrada estandarizada (Excel).

Todo se deriva de ``esquema.py`` (``HOJAS``, ``Columna``, ``Hoja`` y
``VERSION_ESQUEMA``): si el esquema cambia, la plantilla cambia sola.

Estructura del libro generado:

* Primera hoja ``LEEME``: instrucciones. La versión del esquema queda en
  ``LEEME!B3`` (``A3`` contiene la etiqueta "Versión del esquema"), para que el
  importador futuro pueda verificarla. También se guarda en las propiedades
  del libro (``wb.properties.title``).
* Una hoja por cada ``Hoja`` del esquema, en el orden de ``HOJAS``. La fila 1
  tiene los encabezados exactos (``Columna.nombre``) y los datos empiezan en
  la fila 2.

Uso::

    .venv/bin/python -m planificador.io_datos.plantilla [--salida RUTA]
                                                        [--sin-ejemplos]
"""

import argparse
import datetime
from pathlib import Path
from typing import Optional

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from planificador.io_datos.esquema import HOJAS, VERSION_ESQUEMA

RAIZ_REPO = Path(__file__).resolve().parents[2]
SALIDA_POR_DEFECTO = RAIZ_REPO / "salidas" / "plantilla_entrada_BORRADOR.xlsx"

HOJA_LEEME = "LEEME"
CELDA_VERSION = "B3"
ULTIMA_FILA = 500

RELLENO_OBLIGATORIA = PatternFill("solid", fgColor="F4B183")
RELLENO_OPCIONAL = PatternFill("solid", fgColor="BDD7EE")
RELLENO_SECCION = PatternFill("solid", fgColor="D9D9D9")
FUENTE_NEGRITA = Font(bold=True)
FUENTE_EJEMPLO = Font(italic=True, color="808080")
RELLENO_VERDE = PatternFill("solid", bgColor="C6EFCE", fgColor="C6EFCE")
RELLENO_ROJO = PatternFill("solid", bgColor="FFC7CE", fgColor="FFC7CE")

NOMBRE_TIPO = {
    "texto": "Texto",
    "entero": "Número entero",
    "decimal": "Número decimal",
    "fecha": "Fecha (AAAA-MM-DD)",
    "hora": "Hora (HH:MM, 24 h)",
    "opcion": "Una opción de la lista",
}


def _si_no(valor: bool) -> str:
    return "Sí" if valor else "No"


def _ref_hoja(nombre: str) -> str:
    """Nombre de hoja listo para usar en una fórmula."""
    return nombre if nombre.replace("_", "").isalnum() else f"'{nombre}'"


def _valores_permitidos(col) -> str:
    """Texto de 'valores permitidos' para una columna, para el LEEME."""
    if col.opciones:
        return ", ".join(str(o) for o in col.opciones)
    if col.referencia:
        hoja, campo = col.referencia.split(".", 1)
        return f"Un valor de la columna «{campo}» de la hoja «{hoja}»"
    if col.tipo == "entero":
        return "Entero mayor o igual a 0"
    if col.tipo == "decimal":
        return "Número mayor o igual a 0"
    if col.tipo == "fecha":
        return "AAAA-MM-DD"
    if col.tipo == "hora":
        return "HH:MM (24 h)"
    return "Texto libre"


def _letra_columna(hojas, referencia: str) -> Optional[tuple]:
    """Devuelve (hoja, letra) de ``"Hoja.columna"`` o None si no existe."""
    nombre_hoja, nombre_col = referencia.split(".", 1)
    for h in hojas:
        if h.nombre == nombre_hoja:
            for i, c in enumerate(h.columnas, start=1):
                if c.nombre == nombre_col:
                    return nombre_hoja, get_column_letter(i)
    return None


def _validacion(col, hojas) -> Optional[DataValidation]:
    """Construye la validación de datos de una columna (o None)."""
    if col.referencia:
        destino = _letra_columna(hojas, col.referencia)
        if destino is not None:
            hoja, letra = destino
            dv = DataValidation(
                type="list",
                formula1=(f"={_ref_hoja(hoja)}!${letra}$2:${letra}"
                          f"${ULTIMA_FILA}"),
                allow_blank=True,
            )
            dv.errorTitle = "Valor no válido"
            dv.error = (f"Elija un valor que exista en {col.referencia} "
                        "(llene primero esa hoja).")
            return dv
    if col.tipo == "opcion" and col.opciones:
        dv = DataValidation(
            type="list",
            formula1='"' + ",".join(str(o) for o in col.opciones) + '"',
            allow_blank=not col.obligatoria,
        )
        dv.errorTitle = "Valor no válido"
        dv.error = "Elija una de las opciones: " + ", ".join(
            str(o) for o in col.opciones) + "."
    elif col.tipo == "entero":
        dv = DataValidation(type="whole", operator="greaterThanOrEqual",
                            formula1="0", allow_blank=True)
        dv.errorTitle = "Número no válido"
        dv.error = "Escriba un número entero mayor o igual a 0."
    elif col.tipo == "decimal":
        dv = DataValidation(type="decimal", operator="greaterThanOrEqual",
                            formula1="0", allow_blank=True)
        dv.errorTitle = "Número no válido"
        dv.error = "Escriba un número mayor o igual a 0."
    elif col.tipo == "fecha":
        dv = DataValidation(type="date", operator="greaterThan",
                            formula1="36526", allow_blank=True)
        dv.errorTitle = "Fecha no válida"
        dv.error = "Escriba una fecha válida con formato AAAA-MM-DD."
    else:
        return None
    dv.showErrorMessage = True
    return dv


def _valor_ejemplo(col):
    """Valor de ejemplo con el tipo de dato correcto (fechas como date)."""
    valor = col.ejemplo
    if col.tipo == "fecha" and isinstance(valor, str):
        try:
            return datetime.date.fromisoformat(valor)
        except ValueError:
            return valor
    return valor


def _ancho(col) -> int:
    largo = max(len(col.nombre), len(str(col.ejemplo or "")), 12)
    if col.tipo == "opcion" and col.opciones:
        largo = max(largo, max(len(str(o)) for o in col.opciones) + 4)
    return min(largo + 4, 40)


def _escribir_hoja_datos(wb, hoja, hojas, con_ejemplos: bool) -> None:
    """Crea la hoja de datos de ``hoja`` con encabezados y validaciones."""
    ws = wb.create_sheet(hoja.nombre)
    for i, col in enumerate(hoja.columnas, start=1):
        letra = get_column_letter(i)
        celda = ws.cell(row=1, column=i, value=col.nombre)
        celda.font = FUENTE_NEGRITA
        celda.fill = (RELLENO_OBLIGATORIA if col.obligatoria
                      else RELLENO_OPCIONAL)
        celda.alignment = Alignment(horizontal="center", vertical="center")
        texto = f"{col.descripcion}\n" + (
            "OBLIGATORIA" if col.obligatoria else "Opcional")
        celda.comment = Comment(texto, "Plantilla")
        ws.column_dimensions[letra].width = _ancho(col)

        dv = _validacion(col, hojas)
        if dv is not None:
            ws.add_data_validation(dv)
            dv.add(f"{letra}2:{letra}{ULTIMA_FILA}")
        if col.tipo == "fecha":
            for fila in range(2, ULTIMA_FILA + 1):
                ws.cell(row=fila, column=i).number_format = "yyyy-mm-dd"
        elif col.tipo in ("hora", "texto"):
            for fila in range(2, ULTIMA_FILA + 1):
                ws.cell(row=fila, column=i).number_format = "@"

    if con_ejemplos:
        for i, col in enumerate(hoja.columnas, start=1):
            valor = _valor_ejemplo(col)
            if valor is not None:
                celda = ws.cell(row=2, column=i, value=valor)
                celda.font = FUENTE_EJEMPLO

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(hoja.columnas))}1"

    if hoja.tipo == "grilla":
        for i, col in enumerate(hoja.columnas, start=1):
            if col.tipo == "opcion" and col.opciones and "SI" in col.opciones:
                letra = get_column_letter(i)
                rango = f"{letra}2:{letra}{ULTIMA_FILA}"
                ws.conditional_formatting.add(rango, CellIsRule(
                    operator="equal", formula=['"SI"'], fill=RELLENO_VERDE))
                ws.conditional_formatting.add(rango, CellIsRule(
                    operator="equal", formula=['"NO"'], fill=RELLENO_ROJO))


def _escribir_leeme(ws, hojas, con_ejemplos: bool) -> None:
    """Rellena la hoja LEEME con instrucciones derivadas del esquema."""
    fila = 1

    def escribir(valores, negrita=False, relleno=None):
        nonlocal fila
        for j, v in enumerate(valores, start=1):
            c = ws.cell(row=fila, column=j, value=v)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            if negrita:
                c.font = FUENTE_NEGRITA
            if relleno is not None:
                c.fill = relleno
        fila += 1

    ws.cell(row=1, column=1,
            value="Plantilla de entrada — Planificador de horarios"
            ).font = Font(bold=True, size=16)
    fila = 2
    ws.cell(row=2, column=1,
            value=f"BORRADOR v{VERSION_ESQUEMA} — sujeto a cambios"
            ).font = Font(bold=True, color="C00000")
    ws.cell(row=3, column=1, value="Versión del esquema")
    ws.cell(row=3, column=2, value=VERSION_ESQUEMA)
    fila = 5

    escribir(["Propósito"], negrita=True, relleno=RELLENO_SECCION)
    escribir([
        "Este libro es el formato estándar para entregar los datos que el "
        "planificador necesita para construir los horarios del programa "
        "(docentes, módulos, salones, grupos, calendario, etc.)."])
    escribir([
        "Cada hoja es una tabla simple: la fila 1 son los encabezados y sus "
        "datos empiezan en la fila 2. Si todos usan el mismo formato, los "
        "datos se pueden cargar sin reprocesarlos a mano."])
    fila += 1

    escribir(["Reglas generales"], negrita=True, relleno=RELLENO_SECCION)
    reglas = [
        "No cambie los nombres de las hojas ni los encabezados de la fila 1.",
        "Una fila por registro; no deje filas vacías entre registros.",
        "Fechas en formato AAAA-MM-DD (por ejemplo 2026-03-23).",
        "Horas en formato HH:MM de 24 horas (por ejemplo 14:30).",
        "Los identificadores (id) son cortos y sin espacios (por ejemplo "
        "D01, M01, F1).",
        "Encabezado naranja = columna obligatoria; azul = opcional. Pase el "
        "cursor sobre un encabezado para ver su descripción.",
        "Donde hay lista desplegable, elija un valor de la lista.",
    ]
    if con_ejemplos:
        reglas.append(
            "La fila 2 de cada hoja (en gris cursiva) es un EJEMPLO: "
            "bórrela o reemplácela con sus datos reales.")
    for r in reglas:
        escribir(["• " + r])
    fila += 1

    escribir(["Orden sugerido de llenado"], negrita=True,
             relleno=RELLENO_SECCION)
    for n, h in enumerate(hojas, start=1):
        escribir([f"{n}. {h.nombre}"])
    escribir([
        "Llene primero las hojas que son referenciadas por otras (por "
        "ejemplo, Docentes antes de Modulos), pues las listas desplegables "
        "toman sus valores de ellas."])
    fila += 1

    escribir(["Hojas del libro"], negrita=True, relleno=RELLENO_SECCION)
    escribir(["Hoja", "Descripción", "Quién la llena"], negrita=True)
    for h in hojas:
        escribir([h.nombre, h.descripcion, h.quien_llena])
    fila += 1

    escribir(["Columnas por hoja"], negrita=True, relleno=RELLENO_SECCION)
    for h in hojas:
        escribir([f"Hoja «{h.nombre}»"], negrita=True)
        escribir(["Columna", "Obligatoria", "Tipo", "Descripción",
                  "Valores permitidos"], negrita=True)
        for c in h.columnas:
            escribir([c.nombre, _si_no(c.obligatoria),
                      NOMBRE_TIPO.get(c.tipo, c.tipo), c.descripcion,
                      _valores_permitidos(c)])
        fila += 1

    for letra, ancho in zip("ABCDE", (30, 45, 28, 50, 50)):
        ws.column_dimensions[letra].width = ancho


def generar_plantilla(ruta_salida: Path, con_ejemplos: bool = True,
                      hojas=None) -> Path:
    """Genera el libro de plantilla y lo guarda en ``ruta_salida``.

    ``hojas`` permite inyectar un esquema alternativo (pruebas); por defecto
    se usa ``HOJAS`` del esquema. Crea las carpetas intermedias si faltan.
    Devuelve la ruta escrita.
    """
    if hojas is None:
        hojas = HOJAS
    ruta_salida = Path(ruta_salida)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws_leeme = wb.active
    ws_leeme.title = HOJA_LEEME
    wb.properties.title = (
        f"Plantilla de entrada — Planificador de horarios "
        f"(esquema {VERSION_ESQUEMA})")
    _escribir_leeme(ws_leeme, hojas, con_ejemplos)
    for h in hojas:
        _escribir_hoja_datos(wb, h, hojas, con_ejemplos)
    wb.save(ruta_salida)
    return ruta_salida


def leer_encabezados(ruta: Path) -> dict:
    """Lee los encabezados (fila 1) de cada hoja de datos de un libro.

    Devuelve ``{hoja: [encabezados]}`` en el orden del libro, sin ``LEEME``.
    """
    wb = load_workbook(ruta)
    try:
        resultado = {}
        for ws in wb.worksheets:
            if ws.title == HOJA_LEEME:
                continue
            fila = next(ws.iter_rows(min_row=1, max_row=1, values_only=True),
                        ())
            enc = [v for v in fila]
            while enc and enc[-1] is None:
                enc.pop()
            resultado[ws.title] = enc
        return resultado
    finally:
        wb.close()


def main(argv=None) -> int:
    """Punto de entrada de línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Genera la plantilla de entrada (Excel) del planificador.")
    parser.add_argument("--salida", type=Path, default=SALIDA_POR_DEFECTO,
                        help="Ruta del .xlsx a generar.")
    parser.add_argument("--sin-ejemplos", action="store_true",
                        help="No incluir filas de ejemplo.")
    args = parser.parse_args(argv)
    ruta = generar_plantilla(args.salida, con_ejemplos=not args.sin_ejemplos)
    print(f"Plantilla generada: {ruta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
