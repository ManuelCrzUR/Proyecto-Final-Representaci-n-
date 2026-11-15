"""Conversión instancia <-> tablas de edición (módulo puro, sin Streamlit).

Las tablas son ``DataFrame`` de pandas pensados para ``st.data_editor``. La
disponibilidad de los docentes y la ventana de los grupos se editan como
grillas booleanas franjas x días, una por entidad.
"""

from __future__ import annotations

import json
import math
from dataclasses import fields

import pandas as pd

from planificador.core.modelo import (
    Bloque,
    Docente,
    Franja,
    Grupo,
    Instancia,
    Pesos,
    Posicion,
    Salon,
)

from .vistas import etiqueta_dia, etiqueta_franja, hhmm

TIPOS_SESION = ("TEORIA", "TALLER", "PRACTICA")


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def _nulo(x) -> bool:
    """True si ``x`` es None o NaN (valor vacío del editor)."""
    if x is None:
        return True
    try:
        return bool(pd.isna(x))
    except (TypeError, ValueError):
        return False


def _texto(x) -> str:
    return "" if _nulo(x) else str(x).strip()


def _entero_opcional(x, campo: str):
    if _nulo(x) or _texto(x) == "":
        return None
    try:
        return int(float(x))
    except (TypeError, ValueError):
        raise ValueError(f"{campo}: '{x}' no es un entero válido") from None


def _entero(x, campo: str) -> int:
    v = _entero_opcional(x, campo)
    if v is None:
        raise ValueError(f"{campo}: falta el valor")
    return v


def _bool(x) -> bool:
    return False if _nulo(x) else bool(x)


def _hora_a_minutos(texto, campo: str) -> int:
    t = _texto(texto)
    try:
        h, m = t.split(":")
        h, m = int(h), int(m)
    except ValueError:
        raise ValueError(f"{campo}: '{t}' no tiene formato HH:MM") from None
    if not (0 <= h <= 24 and 0 <= m < 60):
        raise ValueError(f"{campo}: '{t}' fuera de rango")
    return h * 60 + m


# --------------------------------------------------------------------------
# Instancia -> tablas
# --------------------------------------------------------------------------

def df_bloques(inst: Instancia) -> pd.DataFrame:
    return pd.DataFrame(
        [{"id": b.id, "modulo_id": b.modulo_id, "duracion": b.duracion,
          "grupos": ",".join(b.grupos), "docente_id": b.docente_id or "",
          "tipo_sesion": b.tipo_sesion, "tipo_salon": b.tipo_salon or "",
          "virtual": b.virtual} for b in inst.bloques],
        columns=["id", "modulo_id", "duracion", "grupos", "docente_id",
                 "tipo_sesion", "tipo_salon", "virtual"])


def df_docentes(inst: Instancia) -> pd.DataFrame:
    return pd.DataFrame(
        [{"id": d.id, "nombre": d.nombre,
          "max_franjas_dia": d.max_franjas_dia} for d in inst.docentes],
        columns=["id", "nombre", "max_franjas_dia"]
    ).astype({"max_franjas_dia": "Int64"})


def df_grupos(inst: Instancia) -> pd.DataFrame:
    return pd.DataFrame(
        [{"id": g.id, "num_estudiantes": g.num_estudiantes,
          "max_franjas_dia": g.max_franjas_dia} for g in inst.grupos],
        columns=["id", "num_estudiantes", "max_franjas_dia"]
    ).astype({"max_franjas_dia": "Int64"})


def df_salones(inst: Instancia) -> pd.DataFrame:
    return pd.DataFrame(
        [{"id": s.id, "tipo": s.tipo, "capacidad": s.capacidad,
          "virtual": s.virtual, "sede": s.sede} for s in inst.salones],
        columns=["id", "tipo", "capacidad", "virtual", "sede"]
    ).astype({"capacidad": "Int64"})


def df_franjas(inst: Instancia) -> pd.DataFrame:
    return pd.DataFrame(
        [{"id": f.id, "inicio": hhmm(f.inicio), "fin": hhmm(f.fin),
          "extrema": f.extrema} for f in inst.franjas],
        columns=["id", "inicio", "fin", "extrema"])


def df_pesos(inst: Instancia) -> pd.DataFrame:
    """Una sola fila; ``lam`` vacío = automático."""
    fila = {c.name: getattr(inst.pesos, c.name) for c in fields(Pesos)}
    return pd.DataFrame([fila])


def df_grilla(inst: Instancia, celdas) -> pd.DataFrame:
    """Grilla booleana franjas x días con las celdas ``(dia, franja)``."""
    celdas = set(celdas)
    return pd.DataFrame(
        [[(d, h) in celdas for d in range(inst.num_dias)]
         for h in range(inst.num_franjas)],
        index=[etiqueta_franja(inst, h) for h in range(inst.num_franjas)],
        columns=[etiqueta_dia(inst, d) for d in range(inst.num_dias)])


def celdas_desde_grilla(df: pd.DataFrame) -> frozenset:
    """Inversa de ``df_grilla`` (por posición, no por etiqueta)."""
    valores = df.to_numpy()
    return frozenset((d, h) for h in range(valores.shape[0])
                     for d in range(valores.shape[1])
                     if _bool(valores[h, d]))


def todas_las_celdas(inst: Instancia) -> frozenset:
    return frozenset((d, h) for d in range(inst.num_dias)
                     for h in range(inst.num_franjas))


def disponibilidades(inst: Instancia) -> dict:
    """docente_id -> frozenset de celdas."""
    return {d.id: d.disponibilidad for d in inst.docentes}


def ventanas(inst: Instancia) -> dict:
    """grupo_id -> frozenset de celdas."""
    return {g.id: g.ventana for g in inst.grupos}


# --------------------------------------------------------------------------
# Tablas -> instancia
# --------------------------------------------------------------------------

def _filas(df: pd.DataFrame):
    """Filas con id no vacío (descarta filas en blanco del editor)."""
    for _, fila in df.iterrows():
        if _texto(fila.get("id")) != "":
            yield fila


def instancia_desde_tablas(base: Instancia, *, bloques: pd.DataFrame,
                           docentes: pd.DataFrame, grupos: pd.DataFrame,
                           salones: pd.DataFrame, franjas: pd.DataFrame,
                           pesos: pd.DataFrame, disp: dict, vent: dict,
                           nombre: str | None = None) -> Instancia:
    """Reconstruye la ``Instancia`` desde las tablas editadas.

    Lanza ``ValueError`` con un mensaje en español si los datos no son
    válidos (incluye las validaciones de ``Instancia.__post_init__``).
    ``disp``/``vent`` dan las celdas por docente/grupo; las entidades nuevas
    sin entrada quedan disponibles en todo el horizonte.
    """
    n_franjas = 0
    fr = []
    for fila in _filas(franjas):
        ini = _hora_a_minutos(fila["inicio"], f"Franja {fila['id']} inicio")
        fin = _hora_a_minutos(fila["fin"], f"Franja {fila['id']} fin")
        if fin <= ini:
            raise ValueError(f"Franja {fila['id']}: el fin debe ser "
                             "posterior al inicio")
        fr.append(Franja(_texto(fila["id"]), ini, fin, _bool(fila["extrema"])))
        n_franjas += 1
    if n_franjas == 0:
        raise ValueError("Debe haber al menos una franja")
    todas = frozenset((d, h) for d in range(base.num_dias)
                      for h in range(n_franjas))

    def celdas_validas(celdas, defecto):
        if celdas is None:
            return defecto
        return frozenset(c for c in celdas if c in todas)

    doc = tuple(
        Docente(_texto(f["id"]), _texto(f["nombre"]),
                celdas_validas(disp.get(_texto(f["id"])), todas),
                _entero_opcional(f["max_franjas_dia"],
                                 f"Docente {f['id']} max_franjas_dia"))
        for f in _filas(docentes))
    gru = tuple(
        Grupo(_texto(f["id"]),
              _entero(f["num_estudiantes"],
                      f"Grupo {f['id']} num_estudiantes"),
              celdas_validas(vent.get(_texto(f["id"])), todas),
              _entero_opcional(f["max_franjas_dia"],
                               f"Grupo {f['id']} max_franjas_dia"))
        for f in _filas(grupos))
    sal = tuple(
        Salon(_texto(f["id"]), _texto(f["tipo"]) or "AULA",
              _entero_opcional(f["capacidad"], f"Salón {f['id']} capacidad"),
              _bool(f["virtual"]), _texto(f["sede"]))
        for f in _filas(salones))
    blo = tuple(
        Bloque(_texto(f["id"]), _texto(f["modulo_id"]),
               _entero(f["duracion"], f"Bloque {f['id']} duración"),
               tuple(g.strip() for g in _texto(f["grupos"]).split(",")
                     if g.strip()),
               _texto(f["docente_id"]) or None,
               _texto(f["tipo_sesion"]) or "TEORIA",
               _texto(f["tipo_salon"]) or None, _bool(f["virtual"]))
        for f in _filas(bloques))
    if len(pesos) != 1:
        raise ValueError("La tabla de pesos debe tener exactamente una fila")
    p = pesos.iloc[0]
    kw = {}
    for c in fields(Pesos):
        valor = p[c.name]
        if c.name == "lam":
            kw[c.name] = None if _nulo(valor) else float(valor)
        else:
            if _nulo(valor):
                raise ValueError(f"Peso {c.name}: falta el valor")
            kw[c.name] = float(valor)
            if math.isnan(kw[c.name]) or kw[c.name] < 0:
                raise ValueError(f"Peso {c.name}: debe ser >= 0")
    ids_f = [f.id for f in fr]
    if len(ids_f) != len(set(ids_f)):
        raise ValueError("IDs repetidos en franjas")
    for b in blo:
        if not b.modulo_id:
            raise ValueError(f"Bloque {b.id}: falta el módulo")
    for g in gru:
        if g.num_estudiantes < 0:
            raise ValueError(f"Grupo {g.id}: estudiantes negativos")
    return Instancia(
        dias=base.dias, franjas=tuple(fr), salones=sal, docentes=doc,
        grupos=gru, bloques=blo, pesos=Pesos(**kw),
        nombre=nombre if nombre is not None else base.nombre)


# --------------------------------------------------------------------------
# JSON (mismo formato que ``io_datos.sintetico.guardar_json``)
# --------------------------------------------------------------------------

def serializar_json(inst: Instancia, solucion: dict | None = None) -> str:
    """Texto JSON con la instancia y, opcionalmente, una solución."""
    datos = {"instancia": inst.a_dict(), "solucion": None}
    if solucion:
        datos["solucion"] = {b: [p.dia, p.franja, p.salon]
                             for b, p in solucion.items()}
    return json.dumps(datos, ensure_ascii=False, indent=1,
                      default=lambda x: sorted(list(c) for c in x))


def deserializar_json(texto: str | bytes) -> tuple:
    """``(instancia, solucion | None)``; acepta también el dict plano."""
    try:
        datos = json.loads(texto)
        crudo = datos["instancia"] if "instancia" in datos else datos
        inst = Instancia.desde_dict(crudo)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"JSON de instancia inválido: {exc}") from exc
    sol = datos.get("solucion") if "instancia" in datos else None
    if sol:
        sol = {b: Posicion(int(p[0]), int(p[1]), p[2])
               for b, p in sol.items()}
    else:
        sol = None
    return inst, sol
