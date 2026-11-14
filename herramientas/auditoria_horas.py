"""Auditoría de horas: calendario académico actual contra la malla curricular.

Herramienta de SOLO LECTURA. Lee la malla curricular y el calendario
académico (hojas de 2026), cuenta las horas realmente programadas por
asignatura y las compara con las horas que exige la malla. El resultado es un
libro de Excel pensado para una persona no técnica (el coordinador).

Uso::

    .venv/bin/python herramientas/auditoria_horas.py

Las rutas por defecto se resuelven desde la raíz del repositorio.
"""

from __future__ import annotations

import argparse
import difflib
import re
import unicodedata
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

RAIZ = Path(__file__).resolve().parent.parent
MALLA_DEFECTO = RAIZ / "data exp" / (
    "MALLA CURRICULARES INVESTIGADORES JUDICIALES 2025 2.xlsx")
CALENDARIO_DEFECTO = RAIZ / "data exp" / (
    "CALENDARIO ACADEMICO ANUAL 2025 - 2026 INVESTIGADORES JUDICIALES 2.xlsx")
SALIDA_DEFECTO = RAIZ / "salidas" / "auditoria_horas.xlsx"
HOJAS_DEFECTO = ("INV.JUD 2026-1", "INVES.JUDICIALES DIURNO 2026-2")
HOJA_MALLA = "INV JUD"

# Tipos de sesión.
CLASE = "CLASE"
TALLER = "TALLER"
PRACTICA = "PRACTICA"
RECESO = "RECESO"
NO_CUENTA = "NO CUENTA"
TIPOS_HORAS = (CLASE, TALLER, PRACTICA)

SIN_EMPAREJAR = "SIN EMPAREJAR"
EXTRAMURAL_HORAS_DEFECTO = 317.0

# Textos que no son asignaturas: no suman horas.
PALABRAS_NO_CUENTA = ("FESTIVO", "SEMANA SANTA", "GRADOS", "VACACIONES")

# Rango horario razonable para una jornada académica (minutos desde 00:00).
MIN_JORNADA = 6 * 60
MAX_JORNADA = 22 * 60

DIAS = ("LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO")

_RE_HORA = re.compile(
    r"(\d{1,2})\s*:\s*(\d{2})(?:\s*([AaPp])\.?\s*[Mm]\b\.?)?")


# ---------------------------------------------------------------------------
# Utilidades de texto
# ---------------------------------------------------------------------------

def sin_tildes(texto: str) -> str:
    """Devuelve el texto sin tildes ni diacríticos."""
    base = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in base if not unicodedata.combining(c))


def separar_docente(texto) -> tuple[str, str]:
    """Separa ``'ASIGNATURA (DOCENTE)'`` en ``(asignatura, docente)``.

    Tolera paréntesis desbalanceados: si falta el cierre, el docente llega
    hasta el final del texto. Si no hay docente devuelve cadena vacía.
    """
    if texto is None:
        return "", ""
    s = str(texto)
    docentes = []
    partes = []
    resto = s
    while "(" in resto:
        antes, _, despues = resto.partition("(")
        partes.append(antes)
        if ")" in despues:
            doc, _, resto = despues.partition(")")
        else:
            doc, resto = despues, ""
        docentes.append(doc.strip())
    partes.append(resto)
    # Un ")" suelto sin apertura se descarta.
    asignatura = " ".join(partes).replace(")", " ")
    asignatura = re.sub(r"\s+", " ", asignatura).strip()
    docente = re.sub(r"\s+", " ", " ".join(d for d in docentes if d)).strip()
    return asignatura, docente


def normalizar(texto, quitar_docente: bool = True) -> str:
    """Normaliza un nombre: mayúsculas, sin tildes, sin docente ni símbolos.

    Los espacios (incluidos saltos de línea) se colapsan en uno solo. Con
    ``quitar_docente=False`` el texto entre paréntesis se conserva (útil para
    los nombres de módulos de la malla).
    """
    if quitar_docente:
        asignatura, _ = separar_docente(texto)
    else:
        asignatura = "" if texto is None else str(texto)
    s = sin_tildes(asignatura).upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# Franjas horarias
# ---------------------------------------------------------------------------

def _a_minutos(hora: int, minuto: int, meridiano: str) -> int:
    """Convierte hora de 12 h con 'AM'/'PM' a minutos desde medianoche."""
    h = hora % 12
    if meridiano == "PM":
        h += 12
    return h * 60 + minuto


def _extraer_tokens(texto: str) -> list[tuple[int, int, str | None]]:
    """Extrae las horas del texto como ``(hora, minuto, meridiano|None)``."""
    tokens = []
    for m in _RE_HORA.finditer(texto):
        mer = None
        if m.group(3):
            mer = m.group(3).upper() + "M"
        tokens.append((int(m.group(1)), int(m.group(2)), mer))
    return tokens


def _opciones(token, invertir: bool) -> list[tuple[int, str]]:
    """Posibles instantes (minutos, meridiano) de un token dentro de jornada."""
    hora, minuto, mer = token
    if mer is None:
        candidatos = ["AM", "PM"]
    else:
        candidatos = [mer]
        if invertir:
            candidatos = ["PM" if mer == "AM" else "AM"]
    res = []
    for c in candidatos:
        t = _a_minutos(hora, minuto, c)
        if MIN_JORNADA <= t <= MAX_JORNADA:
            res.append((t, c))
    return res


def _resolver_par(ini, fin):
    """Resuelve un par de tokens; devuelve (inicio, fin, avisos) o None."""
    intentos = [(False, False), (False, True), (True, False), (True, True)]
    for inv_i, inv_f in intentos:
        mejores = []
        for ti, mi in _opciones(ini, inv_i):
            for tf, mf in _opciones(fin, inv_f):
                if tf > ti:
                    mejores.append((tf - ti, ti, tf, mi, mf))
        if mejores:
            _, ti, tf, mi, mf = min(mejores)
            avisos = []
            if inv_i and ini[2]:
                avisos.append(
                    f"Se corrigió la hora de inicio {ini[0]}:{ini[1]:02d} "
                    f"{ini[2]} a {mi}")
            if inv_f and fin[2]:
                avisos.append(
                    f"Se corrigió la hora de fin {fin[0]}:{fin[1]:02d} "
                    f"{fin[2]} a {mf}")
            return ti, tf, avisos
    return None


def parsear_franjas(texto) -> tuple[list[tuple[int, int]], list[str]]:
    """Parsea una franja que puede tener varios rangos.

    Ejemplo: ``'PRACTICA: 8:00 A 12:00 Y 2:00 A 5:00 PM'`` devuelve dos
    rangos. Los instantes se dan en minutos desde medianoche. Corrige AM/PM
    inconsistentes y deja cada corrección en la lista de advertencias.
    """
    if texto is None:
        return [], ["Franja vacía"]
    tokens = _extraer_tokens(str(texto))
    rangos: list[tuple[int, int]] = []
    avisos: list[str] = []
    if len(tokens) < 2:
        return [], [f"No se pudo leer la franja horaria: {texto!r}"]
    if len(tokens) % 2:
        avisos.append(f"Cantidad impar de horas en la franja: {texto!r}")
    for i in range(0, len(tokens) - 1, 2):
        res = _resolver_par(tokens[i], tokens[i + 1])
        if res is None:
            avisos.append(f"Rango horario inválido en {texto!r}")
            continue
        ini, fin, extra = res
        rangos.append((ini, fin))
        avisos.extend(f"{a} (franja {texto!r})" for a in extra)
    return rangos, avisos


def parsear_franja(texto) -> tuple[int | None, int | None, list[str]]:
    """Parsea una franja simple ``'7:00 A 8:00 AM'``.

    Devuelve ``(inicio, fin, advertencias)`` con inicio y fin en minutos
    desde medianoche (``None`` si no se pudo leer). Si el texto trae varios
    rangos se usa el primero y se avisa; use ``parsear_franjas`` para todos.
    """
    rangos, avisos = parsear_franjas(texto)
    if not rangos:
        return None, None, avisos
    if len(rangos) > 1:
        avisos.append("La franja tiene varios rangos; se devuelve el primero")
    return rangos[0][0], rangos[0][1], avisos


def _hhmm(minutos: int) -> str:
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


# ---------------------------------------------------------------------------
# Malla curricular
# ---------------------------------------------------------------------------

def _num(valor) -> float | None:
    """Devuelve el valor si es numérico (no fórmula ni texto)."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return float(valor)


def leer_malla(ruta, hoja: str = HOJA_MALLA) -> pd.DataFrame:
    """Lee los módulos de la malla y recalcula desde sus valores.

    Un módulo es una fila con nombre en la columna C y un valor numérico en
    D (teoría). Las filas de unidad de competencia y el resumen se excluyen.
    Columnas: fila, n, modulo, modulo_norm, categoria, unidad, teoria,
    trabajo_autonomo, taller, practica, turno. ``df.attrs`` guarda las
    ``advertencias`` (discrepancias de fórmulas) y los ``totales`` recalculados
    contra los declarados en el Excel.
    """
    wb_f = openpyxl.load_workbook(ruta, data_only=False)
    wb_v = openpyxl.load_workbook(ruta, data_only=True)
    ws, wv = wb_f[hoja], wb_v[hoja]
    filas = []
    unidades = {}  # fila de unidad -> (texto, [filas de módulos])
    categoria = ""
    unidad_fila, unidad = None, ""
    for r in range(1, ws.max_row + 1):
        a, b, c, d = (ws.cell(r, k).value for k in (1, 2, 3, 4))
        if isinstance(c, str) and c.strip().upper().startswith(
                "PRACTICA TALLERES"):
            break  # empieza el resumen
        if isinstance(a, str) and a.strip():
            categoria = a.strip()
            if r == 7 or isinstance(b, str):
                unidad_fila, unidad = r, (b or a).strip()
                unidades[r] = (unidad, [])
        elif isinstance(b, str) and not isinstance(c, str):
            if b.strip() not in ("N°",):
                unidad_fila, unidad = r, b.strip()
                unidades[r] = (unidad, [])
        if isinstance(c, str) and c.strip() and _num(d) is not None:
            n = b if isinstance(b, (int, float)) else None
            filas.append({
                "fila": r, "n": n, "modulo": re.sub(r"\s+", " ", c).strip(),
                "modulo_norm": normalizar(c, quitar_docente=False),
                "categoria": categoria,
                "unidad": unidad,
                "teoria": _num(d) or 0.0,
                "trabajo_autonomo": _num(ws.cell(r, 5).value) or 0.0,
                "trabajo_independiente": _num(ws.cell(r, 6).value) or 0.0,
                "taller": _num(ws.cell(r, 7).value) or 0.0,
                "practica": _num(ws.cell(r, 8).value) or 0.0,
                "turno": _num(ws.cell(r, 9).value) or 0.0,
            })
            if unidad_fila is not None:
                unidades[unidad_fila][1].append(len(filas) - 1)
    df = pd.DataFrame(filas)
    df.attrs["advertencias"] = _auditar_formulas_malla(ws, wv, df, unidades)
    df.attrs["totales"] = _totales_malla(wv, df)
    df.attrs["advertencias"].extend(_avisos_totales(df.attrs["totales"]))
    return df


def _auditar_formulas_malla(ws, wv, df, unidades) -> list[dict]:
    """Compara fórmulas de unidades contra la suma real de sus módulos."""
    avisos = []
    columnas = {"D": "teoria", "F": "trabajo_independiente",
                "G": "taller", "H": "practica", "I": "turno"}
    for fila, (nombre, idx) in unidades.items():
        mods = df.iloc[idx] if idx else df.iloc[0:0]
        for col, campo in columnas.items():
            formula = ws[f"{col}{fila}"].value
            if not (isinstance(formula, str) and formula.startswith("=")):
                continue
            declarado = wv[f"{col}{fila}"].value
            real = float(mods[campo].sum()) if len(mods) else 0.0
            if declarado is None:
                declarado = 0
            filas_mod = [int(x) for x in mods["fila"]] if len(mods) else []
            esperado = (f"{col}{min(filas_mod)}:{col}{max(filas_mod)}"
                        if filas_mod else "")
            refs = re.findall(r"[A-Z]+(\d+)(?::[A-Z]+(\d+))?", formula)
            filas_ref = sorted({int(x) for ref in refs for x in ref if x})
            if filas_mod and filas_ref and (
                    filas_ref[0] != min(filas_mod)
                    or filas_ref[-1] != max(filas_mod)):
                avisos.append({
                    "hoja": HOJA_MALLA, "celda": f"{col}{fila}",
                    "descripcion": (
                        f"El rango de la fórmula {formula} no coincide con "
                        f"los módulos de la unidad '{nombre[:60]}' "
                        f"(debería ser {esperado}).")})
            if abs(float(declarado) - real) > 1e-6:
                avisos.append({
                    "hoja": HOJA_MALLA, "celda": f"{col}{fila}",
                    "descripcion": (
                        f"La fórmula {formula} da {declarado:g}, pero la "
                        f"suma real de los módulos de la unidad "
                        f"'{nombre[:60]}' es {real:g}.")})
    return avisos


def _avisos_totales(t: dict) -> list[dict]:
    """Advierte cuando los totales declarados no coinciden con los reales."""
    pares = [("H52", "práctica del instituto", "declarado_practica_instituto",
              "practica_instituto"),
             ("D56", "horas teóricas", "declarado_teoricas", "teoricas"),
             ("D57", "horas prácticas", "declarado_practicas", "practicas"),
             ("D58", "total del programa", "declarado_total", "total")]
    avisos = []
    for celda, nombre, dec, rec in pares:
        if t[dec] is not None and abs(t[dec] - t[rec]) > 1e-6:
            avisos.append({
                "hoja": HOJA_MALLA, "celda": celda,
                "descripcion": (
                    f"El Excel declara {t[dec]:g} h de {nombre}, pero "
                    f"recalculando desde los módulos resultan {t[rec]:g} h.")})
    return avisos


def _totales_malla(wv, df) -> dict:
    """Totales recalculados y declarados en el resumen de la malla."""
    extramural = _num(wv["G54"].value) or EXTRAMURAL_HORAS_DEFECTO
    teoria = float(df["teoria"].sum())
    autonomo = round(0.2 * teoria, 4)
    taller = float(df["taller"].sum())
    practica = float(df["practica"].sum())
    return _con_declarados(wv, {
        "teoria": teoria, "trabajo_autonomo": autonomo, "taller": taller,
        "practica_instituto": practica, "extramural": extramural,
        "teoricas": teoria + autonomo,
        "practicas": taller + practica + extramural,
        "total": teoria + autonomo + taller + practica + extramural,
    })


def _con_declarados(wv, totales: dict) -> dict:
    """Agrega a los totales recalculados los valores declarados."""
    totales.update({
        "declarado_teoricas": _num(wv["D56"].value),
        "declarado_practicas": _num(wv["D57"].value),
        "declarado_total": _num(wv["D58"].value),
        "declarado_taller": _num(wv["G52"].value),
        "declarado_practica_instituto": _num(wv["H52"].value),
    })
    return totales


# ---------------------------------------------------------------------------
# Calendario
# ---------------------------------------------------------------------------

def _resolver_hoja(wb, hoja: str):
    """Encuentra la hoja ignorando espacios dobles o finales."""
    objetivo = re.sub(r"\s+", " ", hoja).strip().upper()
    for nombre in wb.sheetnames:
        if re.sub(r"\s+", " ", nombre).strip().upper() == objetivo:
            return wb[nombre]
    raise KeyError(f"No existe la hoja {hoja!r}. Hojas: {wb.sheetnames}")


def _grupos_dia(ws, fila_enc: int) -> dict[str, int]:
    """Columna inicial de cada día en la fila de encabezado."""
    grupos = {}
    for celda in ws[fila_enc]:
        if isinstance(celda.value, str):
            nombre = normalizar(celda.value)
            if nombre in DIAS and nombre not in grupos:
                grupos[nombre] = celda.column
    return grupos


def _dia_de_columna(grupos: dict[str, int], col: int) -> str | None:
    """Día al que pertenece una columna (grupo de 5-6 columnas)."""
    elegido = None
    for dia, c0 in sorted(grupos.items(), key=lambda kv: kv[1]):
        if col >= c0:
            elegido = dia
    return elegido


def _tipo_y_nombre(texto: str, fila_practica: bool):
    """Clasifica el contenido: (tipo, nombre, es_taller_sin_nombre)."""
    norm = normalizar(texto)
    if norm.startswith("RECESO"):
        return RECESO, norm, False
    if any(norm == p or norm.startswith(p + " ")
           for p in PALABRAS_NO_CUENTA):
        return NO_CUENTA, norm, False
    if re.search(r"\bPRACTICAS?\b(?! SALUDABLES)", norm) or fila_practica:
        return PRACTICA, norm, False
    if norm == "TALLER":
        return TALLER, "", True
    if norm.startswith("TALLER "):
        return TALLER, norm[len("TALLER "):].strip(), False
    if norm.endswith(" Y TALLER"):
        return TALLER, norm[:-len(" Y TALLER")].strip(), False
    return CLASE, norm, False


def leer_calendario_completo(ruta, hoja: str, wb=None):
    """Lee una hoja del calendario y devuelve ``(sesiones, avisos, semanas)``.

    ``sesiones`` es un DataFrame con una fila por celda, franja y rango:
    semana, n_semana, dia, dia_mes, franja, asignatura, docente, tipo, horas,
    celda, inicio, fin. ``avisos`` es una lista de dicts (hoja, celda,
    descripcion). ``semanas`` es una lista de dicts con el texto y el número
    de semana.
    """
    if wb is None:
        wb = openpyxl.load_workbook(ruta)
    ws = _resolver_hoja(wb, hoja)
    nombre_hoja = ws.title
    avisos: list[dict] = []
    if nombre_hoja != hoja:
        avisos.append({"hoja": nombre_hoja, "celda": "",
                       "descripcion": (f"El nombre real de la hoja es "
                                       f"{nombre_hoja!r} (se pidió {hoja!r})")})

    def avisar(celda, texto):
        avisos.append({"hoja": nombre_hoja, "celda": celda,
                       "descripcion": texto})

    origen_fusion = {}
    for rango in ws.merged_cells.ranges:
        origen_fusion[(rango.min_row, rango.min_col)] = rango

    anclas = [c.row for c in ws["A"]
              if isinstance(c.value, str)
              and normalizar(c.value) == "FECHAS"]
    limites = anclas[1:] + [ws.max_row + 1]
    filas_ses: list[dict] = []
    semanas: list[dict] = []
    for n, (r0, r1) in enumerate(zip(anclas, limites), start=1):
        texto_sem = re.sub(r"\s+", " ", str(ws.cell(r0, 4).value or "")).strip()
        semanas.append({"n_semana": n, "semana": texto_sem, "fila": r0})
        fila_enc = next((r for r in range(r0, r1)
                         if _grupos_dia(ws, r)), None)
        if fila_enc is None:
            avisar(f"A{r0}", f"Semana '{texto_sem}' sin encabezado de días")
            continue
        grupos = _grupos_dia(ws, fila_enc)
        nums = {}
        for dia, col in grupos.items():
            v = _num(ws.cell(fila_enc + 1, col).value)
            nums[dia] = int(v) if v is not None else None
        # Franjas de la semana.
        franjas = []
        for r in range(fila_enc + 2, r1):
            a = ws.cell(r, 1).value
            if isinstance(a, str) and a.strip():
                rangos, av = parsear_franjas(a)
                etiqueta = re.sub(r"\s+", " ", a).strip()
                for x in av:
                    avisar(f"A{r}", x)
                franjas.append({
                    "fila": r, "etiqueta": etiqueta, "rangos": rangos,
                    "practica": "PRACTICA" in normalizar(a)})
        por_fila = {f["fila"]: f for f in franjas}
        sesiones_sem: list[dict] = []
        for f in franjas:
            r = f["fila"]
            for celda in ws[r]:
                if celda.column < 4 or not isinstance(celda.value, str):
                    continue
                if not celda.value.strip():
                    continue
                rango = origen_fusion.get((r, celda.column))
                c_min = rango.min_col if rango else celda.column
                c_max = rango.max_col if rango else celda.column
                r_max = rango.max_row if rango else r
                dias_cub = [d for d, c in grupos.items()
                            if c_min <= c <= c_max]
                if not dias_cub:
                    d = _dia_de_columna(grupos, celda.column)
                    if d is None:
                        continue
                    dias_cub = [d]
                if celda.column not in grupos.values() and not rango:
                    avisar(celda.coordinate,
                           "Texto fuera de la primera columna del día; se "
                           "asignó al día correspondiente")
                filas_cub = [x for x in range(r, r_max + 1) if x in por_fila]
                asig_txt, docente = separar_docente(celda.value)
                if celda.value.count("(") != celda.value.count(")"):
                    avisar(celda.coordinate,
                           f"Paréntesis desbalanceados: {celda.value!r}")
                for fr in filas_cub:
                    fran = por_fila[fr]
                    tipo, nombre, sin_nombre = _tipo_y_nombre(
                        celda.value, fran["practica"])
                    if tipo == NO_CUENTA and "GRADOS" in nombre:
                        avisar(celda.coordinate,
                               "'GRADOS' se trata como evento sin horas "
                               "de asignatura")
                    for ini, fin in fran["rangos"]:
                        for dia in dias_cub:
                            sesiones_sem.append({
                                "semana": texto_sem, "n_semana": n,
                                "dia": dia, "dia_mes": nums.get(dia),
                                "franja": fran["etiqueta"],
                                "asignatura": nombre, "docente": docente,
                                "tipo": tipo, "inicio": ini, "fin": fin,
                                "celda": celda.coordinate, "fila": fr,
                                "_sin_nombre": sin_nombre,
                                "_asig_original": asig_txt})
        _completar_talleres(sesiones_sem, avisar)
        filas_ses.extend(sesiones_sem)
    df = pd.DataFrame(filas_ses)
    if df.empty:
        df = pd.DataFrame(columns=[
            "semana", "n_semana", "dia", "dia_mes", "franja", "asignatura",
            "docente", "tipo", "inicio", "fin", "celda", "fila", "horas",
            "choque_horas"])
        return df, avisos, semanas
    df = _calcular_horas(df, avisar)
    df = df.drop(columns=["_sin_nombre", "_asig_original"])
    return df, avisos, semanas


def leer_calendario(ruta, hoja: str) -> pd.DataFrame:
    """Lee una hoja del calendario y devuelve el DataFrame de sesiones.

    Las advertencias y las semanas quedan en ``df.attrs['advertencias']`` y
    ``df.attrs['semanas']``.
    """
    df, avisos, semanas = leer_calendario_completo(ruta, hoja)
    df.attrs["advertencias"] = avisos
    df.attrs["semanas"] = semanas
    return df


def _completar_talleres(sesiones: list[dict], avisar) -> None:
    """Asigna a cada 'TALLER' sin nombre la asignatura de clase del día."""
    ultima: dict[tuple, str] = {}
    for s in sorted(sesiones, key=lambda x: (x["fila"], x["inicio"])):
        clave = (s["n_semana"], s["dia"])
        if s["tipo"] == CLASE and s["asignatura"]:
            ultima[clave] = s["asignatura"]
        elif s["tipo"] == TALLER and s["_sin_nombre"]:
            if clave in ultima:
                s["asignatura"] = ultima[clave]
            else:
                s["asignatura"] = "TALLER SIN ASIGNATURA"
                avisar(s["celda"],
                       f"Taller sin asignatura identificable el "
                       f"{s['dia']} de {s['semana']}")


def _es_practica_externa(fila) -> bool:
    """Práctica en franja propia ('PRACTICA: 8:00 A 12:00...'): sin receso."""
    return fila.tipo == PRACTICA and "PRACTICA" in normalizar(fila.franja)


def _quitar_recesos(ini: int, fin: int, recesos) -> list[tuple[int, int]]:
    """Parte el intervalo ``[ini, fin]`` quitando los recesos que lo cruzan."""
    piezas = [(ini, fin)]
    for a, b in sorted(recesos):
        nuevas = []
        for x, y in piezas:
            if b <= x or a >= y:
                nuevas.append((x, y))
                continue
            if a > x:
                nuevas.append((x, a))
            if b < y:
                nuevas.append((b, y))
        piezas = nuevas
    return piezas


def _calcular_horas(df: pd.DataFrame, avisar) -> pd.DataFrame:
    """Calcula horas por sesión descontando recesos y detecta choques.

    El receso de 10:00 a 10:20 se descuenta de las franjas del instituto que
    lo contienen. Las prácticas en franja propia ('PRACTICA: 8:00 A 12:00 Y
    2:00 A 5:00') se cuentan completas. El choque de un día es la cantidad
    de horas programadas por encima de lo que el horario permite (dos
    actividades a la misma hora).
    """
    horas = {}
    piezas_dia: dict[tuple, list] = {}
    receso_total = 0
    for (n, dia), g in df.groupby(["n_semana", "dia"], sort=False):
        recesos = [(r.inicio, r.fin) for r in g.itertuples()
                   if r.tipo == RECESO]
        for r in g.itertuples():
            if r.tipo not in TIPOS_HORAS:
                horas[r.Index] = 0.0
                continue
            if _es_practica_externa(r):
                piezas = [(r.inicio, r.fin)]
            else:
                piezas = _quitar_recesos(r.inicio, r.fin, recesos)
                receso_total += (r.fin - r.inicio) - sum(
                    y - x for x, y in piezas)
            horas[r.Index] = sum(y - x for x, y in piezas) / 60.0
            piezas_dia.setdefault((n, dia), []).extend(piezas)
    df["horas"] = pd.Series(horas).reindex(df.index).round(4)
    if receso_total:
        avisar("", (f"Receso descontado: {receso_total / 60:g} h en total "
                    "(20 min por franja del instituto que contiene el "
                    "receso de 10:00 a 10:20; las prácticas en franja "
                    "propia no se descuentan)."))
    df["choque_horas"] = 0.0
    for (n, dia), piezas in piezas_dia.items():
        g = df[(df["n_semana"] == n) & (df["dia"] == dia)
               & df["tipo"].isin(TIPOS_HORAS)]
        exceso = round(float(g["horas"].sum()) - _union_horas(piezas), 4)
        if exceso > 0.01:
            df.loc[g.index[0], "choque_horas"] = exceso
            celdas = ", ".join(sorted(set(g["celda"])))
            avisar(celdas, (f"Choque de horario el {dia} de "
                            f"{g.iloc[0]['semana']}: {exceso:g} h "
                            "programadas encima de otra actividad."))
    return df


def _union_horas(intervalos) -> float:
    """Horas cubiertas por la unión de intervalos (minutos)."""
    if not intervalos:
        return 0.0
    ordenados = sorted(intervalos)
    fusion = [list(ordenados[0])]
    for a, b in ordenados[1:]:
        if a <= fusion[-1][1]:
            fusion[-1][1] = max(fusion[-1][1], b)
        else:
            fusion.append([a, b])
    return sum(b - a for a, b in fusion) / 60.0


# ---------------------------------------------------------------------------
# Emparejamiento calendario <-> malla
# ---------------------------------------------------------------------------

_PALABRAS_VACIAS = {"DE", "LA", "EL", "LOS", "LAS", "Y", "O", "E", "EN",
                    "A", "DEL", "CON", "AL", "SEGUN", "ACUERDO", "PARA"}


def _tokens(texto: str) -> set[str]:
    return {t for t in texto.split() if t not in _PALABRAS_VACIAS
            and len(t) > 2}


def _similitud_palabras(a: str, b: str) -> float:
    """Promedio de la mejor similitud de cada palabra de ``a`` en ``b``."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return sum(max(difflib.SequenceMatcher(None, x, y).ratio() for y in tb)
               for x in ta) / len(ta)


def emparejar(nombres_calendario, nombres_malla,
              umbral: float = 0.8, umbral_palabras: float = 0.6
              ) -> pd.DataFrame:
    """Empareja asignaturas del calendario con módulos de la malla.

    Orden de métodos: ``exacta`` (texto normalizado igual), ``contiene``
    (uno contiene al otro; el más corto debe tener al menos 5 letras y el
    candidato debe ser único), ``difusa`` (SequenceMatcher >= umbral) y
    ``palabras`` (coincidencia de palabras clave >= umbral_palabras). Lo que
    no cumple queda ``SIN EMPAREJAR`` y se muestra el mejor candidato solo como
    sugerencia.

    Devuelve columnas: calendario, modulo, metodo, puntaje, sugerencia,
    puntaje_sugerencia.
    """
    malla = list(dict.fromkeys(
        normalizar(m, quitar_docente=False) for m in nombres_malla))
    filas = []
    for original in dict.fromkeys(nombres_calendario):
        nom = normalizar(original)
        mejor, metodo, puntaje = None, SIN_EMPAREJAR, 0.0
        ratios = {m: difflib.SequenceMatcher(None, nom, m).ratio()
                  for m in malla}
        mejor_ratio = max(ratios, key=ratios.get) if ratios else None
        sugerencia = mejor_ratio
        punt_sug = ratios[sugerencia] if sugerencia else 0.0
        extra = {m: _similitud_palabras(nom, m) for m in malla}
        if extra and max(extra.values()) > punt_sug:
            sugerencia = max(extra, key=extra.get)
            punt_sug = extra[sugerencia]
        if nom in ratios:
            mejor, metodo, puntaje = nom, "exacta", 1.0
        else:
            cont = [m for m in malla if len(min(nom, m, key=len)) >= 5
                    and nom and (nom in m or m in nom)]
            if len(cont) == 1:
                mejor, metodo, puntaje = cont[0], "contiene", ratios[cont[0]]
            elif len(cont) > 1:
                metodo = "ambigua"
                sugerencia = max(cont, key=ratios.get)
                punt_sug = ratios[sugerencia]
            if mejor is None and metodo != "ambigua":
                if mejor_ratio and ratios[mejor_ratio] >= umbral:
                    mejor, metodo = mejor_ratio, "difusa"
                    puntaje = ratios[mejor_ratio]
                else:
                    tn = _tokens(nom)
                    jac = {}
                    for m in malla:
                        tm = _tokens(m)
                        if tn and tm:
                            jac[m] = len(tn & tm) / len(tn | tm)
                    if jac:
                        m_j = max(jac, key=jac.get)
                        if jac[m_j] >= umbral_palabras:
                            mejor, metodo, puntaje = (
                                m_j, "palabras", jac[m_j])
        if mejor is None and metodo == "ambigua":
            metodo = "ambigua (varios módulos lo contienen)"
        filas.append({
            "calendario": original, "calendario_norm": nom,
            "modulo": mejor if mejor else SIN_EMPAREJAR,
            "metodo": metodo if mejor else (
                metodo if metodo.startswith("ambigua") else "ninguno"),
            "puntaje": round(puntaje, 3),
            "sugerencia": sugerencia or "",
            "puntaje_sugerencia": round(punt_sug, 3)})
    return pd.DataFrame(filas, columns=[
        "calendario", "calendario_norm", "modulo", "metodo", "puntaje",
        "sugerencia", "puntaje_sugerencia"])


# ---------------------------------------------------------------------------
# Cálculos de auditoría
# ---------------------------------------------------------------------------

def horas_por_asignatura(sesiones: pd.DataFrame) -> pd.DataFrame:
    """Horas por asignatura normalizada y tipo (columnas CLASE/TALLER/...)."""
    base = sesiones[sesiones["tipo"].isin(TIPOS_HORAS)]
    if base.empty:
        return pd.DataFrame(columns=["asignatura", *TIPOS_HORAS])
    tabla = base.pivot_table(index="asignatura", columns="tipo",
                             values="horas", aggfunc="sum", fill_value=0.0)
    for t in TIPOS_HORAS:
        if t not in tabla:
            tabla[t] = 0.0
    return tabla[list(TIPOS_HORAS)].reset_index()


def auditar(ruta_malla, ruta_calendario, hojas=HOJAS_DEFECTO) -> dict:
    """Ejecuta toda la auditoría y devuelve un diccionario de resultados."""
    malla = leer_malla(ruta_malla)
    wb = openpyxl.load_workbook(ruta_calendario)
    resultados = {"malla": malla, "hojas": {}, "advertencias": list(
        malla.attrs["advertencias"]), "totales_malla": malla.attrs["totales"]}
    for hoja in hojas:
        ses, avisos, semanas = leer_calendario_completo(
            ruta_calendario, hoja, wb=wb)
        real = _resolver_hoja(wb, hoja).title
        ses.attrs["hoja"] = real
        agregado = horas_por_asignatura(ses)
        emp = emparejar(agregado["asignatura"], malla["modulo"])
        mapa = dict(zip(emp["calendario"], emp["modulo"]))
        agregado["modulo_norm"] = agregado["asignatura"].map(mapa)
        resultados["hojas"][real] = {
            "sesiones": ses, "agregado": agregado, "emparejamiento": emp,
            "semanas": semanas}
        resultados["advertencias"].extend(avisos)
        for r in emp.itertuples():
            if r.metodo in ("difusa", "palabras", "contiene"):
                resultados["advertencias"].append({
                    "hoja": real, "celda": "",
                    "descripcion": (
                        f"Emparejamiento aproximado ({r.metodo}, puntaje "
                        f"{r.puntaje}): '{r.calendario}' -> '{r.modulo}'. "
                        "Conviene confirmarlo.")})
    return resultados


def tabla_por_modulo(resultados: dict) -> pd.DataFrame:
    """Tabla módulo x (malla, programado por hoja, diferencia)."""
    malla = resultados["malla"]
    filas = []
    for m in malla.itertuples():
        fila = {"n": m.n, "modulo": m.modulo, "unidad": m.unidad,
                "malla_teoria": m.teoria, "malla_taller": m.taller,
                "malla_practica": m.practica}
        for hoja, datos in resultados["hojas"].items():
            ag = datos["agregado"]
            sel = ag[ag["modulo_norm"] == m.modulo_norm]
            prog = {campo: round(float(sel[tipo].sum()), 2) if len(sel)
                    else 0.0
                    for tipo, campo in ((CLASE, "teoria"),
                                        (TALLER, "taller"),
                                        (PRACTICA, "practica"))}
            for campo, valor in prog.items():
                fila[f"{hoja}|prog_{campo}"] = valor
            for campo, valor in prog.items():
                fila[f"{hoja}|dif_{campo}"] = round(
                    valor - getattr(m, campo), 2)
        filas.append(fila)
    return pd.DataFrame(filas)


def resumen_hoja(datos: dict, malla_tot: dict) -> dict:
    """Totales por tipo, semanas y diferencias de una hoja del calendario."""
    ses = datos["sesiones"]
    por_tipo = {t: round(float(ses.loc[ses["tipo"] == t, "horas"].sum()), 2)
                for t in TIPOS_HORAS}
    por_semana = ses.groupby("n_semana")["horas"].sum() if len(ses) else {}
    n_sem = len(datos["semanas"])
    sin_clase = [s["semana"] for s in datos["semanas"]
                 if float(por_semana.get(s["n_semana"], 0.0)) == 0.0]
    ag = datos["agregado"]
    emparejado = ag["modulo_norm"] != SIN_EMPAREJAR
    return {
        "por_tipo": por_tipo, "total": round(sum(por_tipo.values()), 2),
        "semanas": n_sem, "semanas_sin_clase": sin_clase,
        "choque": round(float(ses["choque_horas"].sum()), 2)
        if len(ses) else 0.0,
        "practica_sin_modulo": round(float(
            ag.loc[~emparejado, PRACTICA].sum()), 2),
        "practica_con_modulo": round(float(
            ag.loc[emparejado, PRACTICA].sum()), 2),
        "malla": malla_tot,
    }


# ---------------------------------------------------------------------------
# Reporte en Excel
# ---------------------------------------------------------------------------

_NEGRITA = Font(bold=True)
_ENCABEZADO = PatternFill("solid", fgColor="D9E1F2")
_TITULO = Font(bold=True, size=14)


def _encabezado(ws, fila: int = 1) -> None:
    for c in ws[fila]:
        if c.value is not None:
            c.font = _NEGRITA
            c.fill = _ENCABEZADO
            c.alignment = Alignment(wrap_text=True, vertical="center")


def _anchos(ws, anchos: dict[str, float]) -> None:
    for col, ancho in anchos.items():
        ws.column_dimensions[col].width = ancho


def _hoja_tabla(wb, nombre, df: pd.DataFrame, anchos=None):
    ws = wb.create_sheet(nombre)
    ws.append(list(df.columns))
    for fila in df.itertuples(index=False):
        ws.append([None if (isinstance(v, float) and pd.isna(v)) else v
                   for v in fila])
    _encabezado(ws)
    ws.freeze_panes = "A2"
    if anchos:
        _anchos(ws, anchos)
    return ws


def _hoja_resumen(wb, resultados: dict) -> None:
    ws = wb.active
    ws.title = "Resumen"
    mt = resultados["totales_malla"]
    hojas = list(resultados["hojas"].items())
    ws.append(["Auditoría de horas: calendario vs. malla curricular"])
    ws["A1"].font = _TITULO
    ws.append(["Diferencia = programado - malla. Negativo: faltan horas. "
               "Positivo: sobran horas."])
    ws.append([])
    ws.append(["Concepto", "Malla curricular",
               *[h for h, _ in hojas]])
    _encabezado(ws, 4)
    res = {h: resumen_hoja(d, mt) for h, d in hojas}
    filas = [
        ("Horas de clase (teoría)", mt["teoria"], CLASE),
        ("Horas de taller", mt["taller"], TALLER),
        ("Horas de práctica (institucional + extramural)",
         mt["practica_instituto"] + mt["extramural"], PRACTICA),
    ]
    for nombre, valor_malla, tipo in filas:
        ws.append([nombre, valor_malla,
                   *[res[h]["por_tipo"][tipo] for h, _ in hojas]])
    total_malla_pres = mt["teoria"] + mt["taller"] + \
        mt["practica_instituto"] + mt["extramural"]
    ws.append(["TOTAL horas presenciales (sin trabajo autónomo)",
               total_malla_pres, *[res[h]["total"] for h, _ in hojas]])
    ws.append(["Trabajo autónomo (20 % de la teoría; no se programa)",
               mt["trabajo_autonomo"], *["n/a" for _ in hojas]])
    ws.append(["TOTAL de la malla con trabajo autónomo", mt["total"],
               *["n/a" for _ in hojas]])
    ws.append([])
    ws.append(["Diferencias (programado - malla)"])
    ws.cell(ws.max_row, 1).font = _NEGRITA
    for nombre, valor_malla, tipo in filas:
        ws.append([nombre, "", *[round(res[h]["por_tipo"][tipo]
                                       - valor_malla, 2) for h, _ in hojas]])
    ws.append(["TOTAL presencial", "",
               *[round(res[h]["total"] - total_malla_pres, 2)
                 for h, _ in hojas]])
    ws.append([])
    ws.append(["Calendario", "", *[h for h, _ in hojas]])
    _encabezado(ws, ws.max_row)
    ws.append(["Número de semanas", "",
               *[res[h]["semanas"] for h, _ in hojas]])
    ws.append(["Semanas sin clase (0 horas)", "",
               *[len(res[h]["semanas_sin_clase"]) for h, _ in hojas]])
    ws.append(["Horas con choque de horario (doble programación)", "",
               *[res[h]["choque"] for h, _ in hojas]])
    ws.append(["Horas de práctica no ligadas a un módulo", "",
               *[res[h]["practica_sin_modulo"] for h, _ in hojas]])
    ws.append([])
    ws.append(["Lectura para el coordinador"])
    ws.cell(ws.max_row, 1).font = _NEGRITA
    for h, _ in hojas:
        r = res[h]
        falta = round(total_malla_pres - r["total"], 1)
        signo = "faltan" if falta > 0 else "sobran"
        ws.append([
            f"En '{h}' hay {r['total']:g} h presenciales programadas "
            f"(clase {r['por_tipo'][CLASE]:g}, taller "
            f"{r['por_tipo'][TALLER]:g}, práctica "
            f"{r['por_tipo'][PRACTICA]:g}) frente a {total_malla_pres:g} h "
            f"de la malla: {signo} {abs(falta):g} h."])
        if r["semanas_sin_clase"]:
            ws.append(["   Semanas sin clase: "
                       + "; ".join(r["semanas_sin_clase"])])
    ws.append([
        "Nota: la malla declara 1800 h en total (900 teóricas con trabajo "
        "autónomo y 900 prácticas). Aquí se recalcula desde los módulos "
        f"y resulta: teóricas {mt['teoricas']:g}, prácticas "
        f"{mt['practicas']:g}, total {mt['total']:g}. "
        "Ver hoja 'Advertencias'."])
    _anchos(ws, {"A": 62, "B": 20, "C": 26, "D": 26})
    ws.freeze_panes = "A2"
    for fila in ws.iter_rows(min_row=1):
        for c in fila:
            if isinstance(c.value, str) and len(c.value) > 70 and c.column == 1:
                c.alignment = Alignment(wrap_text=False)


def _hoja_por_modulo(wb, resultados: dict) -> None:
    tabla = tabla_por_modulo(resultados)
    ws = wb.create_sheet("Por modulo")
    hojas = list(resultados["hojas"])
    cab1 = ["N°", "Módulo", "Unidad de competencia", "Malla: teoría",
            "Malla: taller", "Malla: práctica"]
    for h in hojas:
        cab1 += [f"{h}: clase", f"{h}: taller", f"{h}: práctica",
                 f"{h}: dif. clase", f"{h}: dif. taller",
                 f"{h}: dif. práctica"]
    ws.append(cab1)
    for r in tabla.itertuples(index=False):
        valores = list(r)
        ws.append([None if (isinstance(v, float) and pd.isna(v)) else v
                   for v in valores])
    # Fila de práctica extramural.
    mt = resultados["totales_malla"]
    extra = [None, "PRÁCTICAS INTEGRALES - EXTRAMURAL (sin módulo)", "",
             0, 0, mt["extramural"]]
    for h in hojas:
        sin = resultados["hojas"][h]["agregado"]
        p = round(float(sin.loc[sin["modulo_norm"] == SIN_EMPAREJAR,
                                PRACTICA].sum()), 2)
        extra += [0, 0, p, 0, 0, round(p - mt["extramural"], 2)]
    ws.append(extra)
    _encabezado(ws)
    ws.freeze_panes = "A2"
    _anchos(ws, {"A": 5, "B": 60, "C": 40})
    for i in range(4, len(cab1) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 14
    ws.row_dimensions[1].height = 45
    ultima = ws.max_row
    rojo = PatternFill("solid", bgColor="F8CBAD", fgColor="F8CBAD")
    verde = PatternFill("solid", bgColor="C6EFCE", fgColor="C6EFCE")
    ambar = PatternFill("solid", bgColor="FFE699", fgColor="FFE699")
    for h_i in range(len(hojas)):
        for k in range(3):
            col = get_column_letter(7 + h_i * 6 + 3 + k)
            rango = f"{col}2:{col}{ultima}"
            ws.conditional_formatting.add(rango, FormulaRule(
                formula=[f"AND(ISNUMBER({col}2),{col}2<-1)"], fill=rojo))
            ws.conditional_formatting.add(rango, FormulaRule(
                formula=[f"AND(ISNUMBER({col}2),ABS({col}2)<=1)"],
                fill=verde))
            ws.conditional_formatting.add(rango, FormulaRule(
                formula=[f"AND(ISNUMBER({col}2),{col}2>1)"], fill=ambar))
    ws.cell(ultima + 2, 2, "Rojo: faltan horas. Verde: cuadra (+-1 h). "
            "Ámbar: sobran horas.")
    ws.cell(ultima + 3, 2, (
        "Las horas de práctica del calendario no indican a qué módulo "
        "pertenecen; por eso la práctica por módulo sale en 0 y la práctica "
        "se compara en conjunto en la fila de práctica extramural y en la "
        "hoja Resumen."))


def _hoja_sin_emparejar(wb, resultados: dict) -> None:
    ws = wb.create_sheet("Sin emparejar")
    ws.append(["Origen", "Hoja del calendario", "Nombre", "Clase (h)",
               "Taller (h)", "Práctica (h)", "Mejor candidato (no aceptado)",
               "Puntaje del candidato", "Nota"])
    for hoja, datos in resultados["hojas"].items():
        emp = datos["emparejamiento"]
        ag = datos["agregado"].set_index("asignatura")
        for r in emp[emp["modulo"] == SIN_EMPAREJAR].itertuples():
            fila = ag.loc[r.calendario]
            ws.append(["Calendario sin módulo", hoja, r.calendario,
                       round(float(fila[CLASE]), 2),
                       round(float(fila[TALLER]), 2),
                       round(float(fila[PRACTICA]), 2),
                       r.sugerencia, r.puntaje_sugerencia, r.metodo])
    for hoja, datos in resultados["hojas"].items():
        usados = set(datos["agregado"]["modulo_norm"].dropna())
        for m in resultados["malla"].itertuples():
            if m.modulo_norm not in usados:
                ws.append(["Módulo de la malla sin programar", hoja,
                           m.modulo, "", "", "", "", "",
                           f"Malla: teoría {m.teoria:g}, taller "
                           f"{m.taller:g}, práctica {m.practica:g}"])
    _encabezado(ws)
    ws.freeze_panes = "A2"
    _anchos(ws, {"A": 32, "B": 32, "C": 60, "D": 11, "E": 11, "F": 12,
                 "G": 50, "H": 14, "I": 50})


def _hoja_emparejamiento(wb, resultados: dict) -> None:
    ws = wb.create_sheet("Emparejamiento")
    ws.append(["Hoja del calendario", "Asignatura en el calendario",
               "Módulo de la malla", "Método", "Puntaje"])
    for hoja, datos in resultados["hojas"].items():
        for r in datos["emparejamiento"].itertuples():
            ws.append([hoja, r.calendario, r.modulo, r.metodo, r.puntaje])
    _encabezado(ws)
    ws.freeze_panes = "A2"
    _anchos(ws, {"A": 32, "B": 60, "C": 60, "D": 30, "E": 10})


def _hoja_advertencias(wb, resultados: dict) -> None:
    ws = wb.create_sheet("Advertencias")
    ws.append(["Hoja", "Celda", "Descripción"])
    for a in resultados["advertencias"]:
        ws.append([a["hoja"], a["celda"], a["descripcion"]])
    _encabezado(ws)
    ws.freeze_panes = "A2"
    _anchos(ws, {"A": 32, "B": 18, "C": 120})


def _hoja_metodologia(wb) -> None:
    ws = wb.create_sheet("Metodologia")
    ws.append(["Metodología"])
    ws["A1"].font = _NEGRITA
    ws.freeze_panes = "A2"
    parrafos = [
        "Esta auditoría es de solo lectura: no modifica ningún archivo "
        "original.",
        "Malla: se detectan los módulos como filas con nombre en la columna "
        "C y teoría numérica en D. Los totales se recalculan sumando los "
        "módulos (no se usan las fórmulas del Excel) y se reportan como "
        "advertencia las fórmulas cuyo resultado no coincide.",
        "Calendario: cada semana empieza en una fila 'FECHAS'. Para cada día "
        "y franja horaria se lee la asignatura. Las celdas combinadas que "
        "abarcan varias franjas cuentan las horas de cada franja cubierta. "
        "Las franjas con AM/PM inconsistente se corrigen (por ejemplo "
        "'11:20 A 12:20 AM' pasa a PM) y cada corrección queda en "
        "'Advertencias'.",
        "Receso: la franja de 7:00 a 12:20 contiene el receso de 10:00 a "
        "10:20 y se descuentan esos 20 minutos. Las prácticas de franja "
        "propia ('PRACTICA: 8:00 A 12:00 Y 2:00 A 5:00') se cuentan "
        "completas (7 h). RECESO, FESTIVO, SEMANA SANTA y GRADOS no suman "
        "horas.",
        "Tipos: CLASE (teoría), TALLER (celdas que empiezan por 'TALLER' o "
        "terminan en 'Y TALLER'; un 'TALLER' sin nombre se atribuye a la "
        "asignatura de clase del mismo día) y PRACTICA (texto con la palabra "
        "PRACTICA o franja rotulada 'PRACTICA'). Esta última no incluye "
        "'Prácticas saludables', que es un módulo.",
        "Emparejamiento: nombre normalizado idéntico (exacta); si no, uno "
        "contiene al otro (contiene); si no, similitud de texto >= 0.8 "
        "(difusa); si no, coincidencia de palabras clave >= 0.6 (palabras). "
        "Los demás quedan 'SIN EMPAREJAR'; no se inventa ningún vínculo.",
        "Comparación: horas de la malla (teoría, taller, práctica) contra "
        "horas programadas. Diferencia = programado - malla. Las horas de "
        "práctica sin módulo se comparan con las 317 h de práctica "
        "extramural de la malla.",
        "Choques: se avisa cuando dos actividades del mismo día se solapan "
        "en horario (por ejemplo, clase de 7:00-12:20 y práctica de "
        "8:00-12:00). Esas horas se cuentan como programadas pero se "
        "reportan aparte.",
    ]
    for p in parrafos:
        ws.append([p])
    ws.column_dimensions["A"].width = 130
    for fila in ws.iter_rows(min_row=2):
        fila[0].alignment = Alignment(wrap_text=True, vertical="top")


def generar_reporte(resultados: dict, ruta_salida) -> Path:
    """Escribe el libro de auditoría en ``ruta_salida`` y devuelve la ruta."""
    ruta = Path(ruta_salida)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    _hoja_resumen(wb, resultados)
    _hoja_por_modulo(wb, resultados)
    _hoja_sin_emparejar(wb, resultados)
    _hoja_emparejamiento(wb, resultados)
    _hoja_advertencias(wb, resultados)
    _hoja_metodologia(wb)
    wb.save(ruta)
    return ruta


def main(argv=None) -> int:
    """Punto de entrada de línea de comandos."""
    p = argparse.ArgumentParser(
        description="Auditoría de horas: calendario vs. malla (solo lectura)")
    p.add_argument("--malla", default=str(MALLA_DEFECTO))
    p.add_argument("--calendario", default=str(CALENDARIO_DEFECTO))
    p.add_argument("--salida", default=str(SALIDA_DEFECTO))
    p.add_argument("--hojas", nargs="+", default=list(HOJAS_DEFECTO))
    args = p.parse_args(argv)
    resultados = auditar(args.malla, args.calendario, tuple(args.hojas))
    ruta = generar_reporte(resultados, args.salida)
    mt = resultados["totales_malla"]
    print(f"Malla recalculada: teoría {mt['teoria']:g}, taller "
          f"{mt['taller']:g}, práctica {mt['practica_instituto']:g}, "
          f"extramural {mt['extramural']:g}, total {mt['total']:g}")
    for hoja, datos in resultados["hojas"].items():
        r = resumen_hoja(datos, mt)
        emp = datos["emparejamiento"]
        sin = int((emp["modulo"] == SIN_EMPAREJAR).sum())
        print(f"{hoja}: {r['por_tipo']} total {r['total']:g}; semanas "
              f"{r['semanas']}, sin clase {len(r['semanas_sin_clase'])}; "
              f"asignaturas sin emparejar {sin}/{len(emp)}")
    print(f"Advertencias: {len(resultados['advertencias'])}")
    print(f"Reporte: {ruta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
