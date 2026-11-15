"""Lógica no visual de las grillas de horario (módulo puro, sin Streamlit).

Convierte una asignación (bloque_id -> Posicion) en una ``Grilla`` por vista
(salón, docente o grupo), marca las celdas que violan disponibilidad,
ventana o conflicto, y la dibuja como tabla HTML. Todo es testeable sin la
interfaz.
"""

from __future__ import annotations

import colorsys
import html
from dataclasses import dataclass, field

from planificador.core.conflictos import construir_conflictos
from planificador.core.modelo import Instancia, celdas_de

DIAS_ES = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
VISTAS = ("Salón", "Docente", "Grupo")

EXPLICACIONES = {
    "expandir": "Se expande un nodo: se toma de la frontera y se generan sus "
                "sucesores (cada posición posible del siguiente bloque).",
    "add": "Se ubica un bloque en una posición (día, franja, salón).",
    "del": "Se quita un bloque que estaba ubicado (deshacer).",
    "podar": "Poda: el nodo se descarta porque un dominio quedó vacío o "
             "porque no puede mejorar.",
    "retroceder": "Retroceso: la búsqueda vuelve un nivel atrás para probar "
                  "otra alternativa.",
    "frontera": "Resumen de la frontera (o haz): cuántos nodos esperan ser "
                "expandidos.",
    "mejora": "Se encontró un estado mejor (menor F) que el mejor conocido.",
    "solucion": "Se alcanzó la meta: horario sin violaciones duras (v = 0).",
    "fin": "La búsqueda terminó.",
}

MOTIVOS = {
    "disponibilidad": "docente fuera de su disponibilidad",
    "ventana": "grupo fuera de su ventana",
    "conflicto": "cruce con otro bloque (mismo docente o grupo)",
}


# --------------------------------------------------------------------------
# Etiquetas
# --------------------------------------------------------------------------

def hhmm(minutos: int) -> str:
    """Minutos desde las 00:00 como ``HH:MM``."""
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def etiqueta_franja(instancia: Instancia, h: int) -> str:
    """Etiqueta con horas reales de la franja ``h``."""
    f = instancia.franjas[h]
    return f"{f.id} {hhmm(f.inicio)}-{hhmm(f.fin)}"


def etiqueta_dia(instancia: Instancia, d: int) -> str:
    """Etiqueta corta de un día: nombre de la semana y índice."""
    dia = instancia.dias[d]
    nombre = DIAS_ES[dia.dia_semana % 7]
    extra = f" {dia.fecha}" if dia.fecha else ""
    return f"{nombre} (d{d}){extra}"


def semanas(instancia: Instancia) -> list:
    """Semanas distintas del horizonte, en orden."""
    return sorted({d.semana for d in instancia.dias})


def dias_de_semana(instancia: Instancia, semana: int) -> list:
    """Índices de los días de una semana."""
    return [d.indice for d in instancia.dias if d.semana == semana]


def color_modulo(instancia: Instancia, modulo_id: str) -> str:
    """Color pastel determinista por módulo (según su orden de aparición)."""
    modulos = sorted({b.modulo_id for b in instancia.bloques})
    k = modulos.index(modulo_id) if modulo_id in modulos else 0
    tono = (k * 0.381966) % 1.0  # razón áurea: tonos bien separados
    r, g, b = colorsys.hls_to_rgb(tono, 0.82, 0.55)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


# --------------------------------------------------------------------------
# Violaciones por celda
# --------------------------------------------------------------------------

def violaciones_por_celda(instancia: Instancia, asignacion: dict,
                          conflictos: dict | None = None) -> dict:
    """Marcas de violación por ``(bloque, dia, franja)``.

    Valor: lista de textos ``"disponibilidad"``, ``"ventana:G"`` o
    ``"conflicto:OTRO"``. Los conteos coinciden con el validador:
    disponibilidad = #marcas de ese tipo; ventana = #marcas; conflicto =
    #marcas / 2 (cada par se marca en ambos bloques).
    """
    if conflictos is None:
        conflictos = construir_conflictos(instancia)
    ocupa = {}
    for bid, pos in asignacion.items():
        if bid in instancia.bloque:
            ocupa[bid] = set(celdas_de(pos, instancia.bloque[bid].duracion))
    marcas: dict = {}

    def poner(bid, celda, motivo):
        marcas.setdefault((bid, celda[0], celda[1]), []).append(motivo)

    for bid, celdas in ocupa.items():
        b = instancia.bloque[bid]
        if b.docente_id is not None:
            disp = instancia.docente[b.docente_id].disponibilidad
            for c in sorted(celdas):
                if c not in disp:
                    poner(bid, c, "disponibilidad")
        for g in b.grupos:
            ventana = instancia.grupo[g].ventana
            for c in sorted(celdas):
                if c not in ventana:
                    poner(bid, c, f"ventana:{g}")
        for otro in conflictos.get(bid, ()):
            if otro in ocupa:
                for c in sorted(celdas & ocupa[otro]):
                    poner(bid, c, f"conflicto:{otro}")
    return marcas


def resumen_marcas(marcas: dict) -> dict:
    """Conteo de violaciones por tipo (``conflicto`` en pares)."""
    cuenta = {"disponibilidad": 0, "ventana": 0, "conflicto": 0}
    for lista in marcas.values():
        for m in lista:
            cuenta[m.split(":")[0]] += 1
    cuenta["conflicto"] //= 2
    return cuenta


# --------------------------------------------------------------------------
# Grilla
# --------------------------------------------------------------------------

@dataclass
class CeldaBloque:
    """Un bloque dibujado en una celda de la grilla."""

    bloque_id: str
    modulo_id: str
    texto: str
    detalle: str
    color: str
    resaltado: bool = False
    movido: bool = False
    marcas: list = field(default_factory=list)

    @property
    def malo(self) -> bool:
        return bool(self.marcas)


@dataclass
class Grilla:
    """Cuadrícula franjas (filas) x días (columnas)."""

    dias: list
    filas: list
    etiquetas_dias: list
    etiquetas_filas: list
    celdas: dict  # (dia, franja) -> list[CeldaBloque]

    @property
    def num_bloques_dibujados(self) -> int:
        """Número de (bloque, celda) dibujados."""
        return sum(len(v) for v in self.celdas.values())


def entidades(instancia: Instancia, vista: str) -> list:
    """Ids seleccionables para una vista."""
    if vista == "Salón":
        return [s.id for s in instancia.salones]
    if vista == "Docente":
        return [d.id for d in instancia.docentes]
    if vista == "Grupo":
        return [g.id for g in instancia.grupos]
    raise ValueError(f"Vista desconocida: {vista}")


def bloques_de_vista(instancia: Instancia, asignacion: dict, vista: str,
                     entidad: str) -> list:
    """Bloques ubicados que pertenecen a la entidad de la vista."""
    salida = []
    for bid in sorted(asignacion):
        b = instancia.bloque.get(bid)
        if b is None:
            continue
        if vista == "Salón":
            ok = asignacion[bid].salon == entidad
        elif vista == "Docente":
            ok = b.docente_id == entidad
        elif vista == "Grupo":
            ok = entidad in b.grupos
        else:
            raise ValueError(f"Vista desconocida: {vista}")
        if ok:
            salida.append(bid)
    return salida


def _texto_bloque(instancia, bid, pos, vista) -> tuple:
    b = instancia.bloque[bid]
    docente = b.docente_id or "sin docente"
    grupos = ",".join(b.grupos) or "-"
    if vista == "Salón":
        corto = f"{docente} · {grupos}"
    elif vista == "Docente":
        corto = f"{grupos} · {pos.salon}"
    else:
        corto = f"{docente} · {pos.salon}"
    detalle = (f"{bid} ({b.modulo_id}) docente={docente} grupos={grupos} "
               f"salón={pos.salon} duración={b.duracion}")
    return corto, detalle


def construir_grilla(instancia: Instancia, asignacion: dict, vista: str,
                     entidad: str, *, resaltado: str | None = None,
                     movidos=frozenset(), dias: list | None = None,
                     conflictos: dict | None = None,
                     marcas: dict | None = None) -> Grilla:
    """Grilla de una entidad (salón, docente o grupo) para ``asignacion``.

    ``dias``: subconjunto de días a mostrar (p. ej. una semana); por omisión
    todos. Cada bloque aparece en cada celda que ocupa. Las celdas fuera del
    rango del horizonte se omiten.
    """
    if marcas is None:
        marcas = violaciones_por_celda(instancia, asignacion, conflictos)
    dias = list(range(instancia.num_dias)) if dias is None else list(dias)
    filas = list(range(instancia.num_franjas))
    celdas: dict = {}
    for bid in bloques_de_vista(instancia, asignacion, vista, entidad):
        b = instancia.bloque[bid]
        pos = asignacion[bid]
        corto, detalle = _texto_bloque(instancia, bid, pos, vista)
        color = color_modulo(instancia, b.modulo_id)
        for (d, h) in celdas_de(pos, b.duracion):
            if d not in dias or not 0 <= h < instancia.num_franjas:
                continue
            m = list(marcas.get((bid, d, h), []))
            texto = corto if h == pos.franja else "↳ " + b.modulo_id
            celdas.setdefault((d, h), []).append(CeldaBloque(
                bloque_id=bid, modulo_id=b.modulo_id, texto=texto,
                detalle=detalle, color=color, resaltado=(bid == resaltado),
                movido=(bid in movidos), marcas=m))
    return Grilla(
        dias=dias, filas=filas,
        etiquetas_dias=[etiqueta_dia(instancia, d) for d in dias],
        etiquetas_filas=[etiqueta_franja(instancia, h) for h in filas],
        celdas=celdas)


def bloques_movidos(vigente: dict, final: dict) -> frozenset:
    """Bloques del horario vigente cuya posición cambió o quedaron sin ubicar."""
    return frozenset(b for b, p in vigente.items() if final.get(b) != p)


def _html_bloque(c: CeldaBloque, compacta: bool) -> str:
    estilo = [f"background:{c.color}", "color:#1b1b1b", "border-radius:4px",
              "padding:1px 3px", "margin:1px 0",
              f"font-size:{'0.62rem' if compacta else '0.74rem'}",
              "line-height:1.15"]
    if c.malo:
        estilo += ["background:#f4a3a3", "border:2px solid #c0152b"]
    else:
        estilo.append("border:1px solid rgba(0,0,0,0.15)")
    if c.resaltado:
        estilo += ["outline:3px solid #1f3bff", "box-shadow:0 0 6px #1f3bff"]
    if c.movido:
        estilo += ["border:2px dashed #b35900"]
    tip = c.detalle
    if c.marcas:
        tip += " | problemas: " + "; ".join(c.marcas)
    return (f'<div title="{html.escape(tip, quote=True)}" '
            f'style="{";".join(estilo)}"><b>{html.escape(c.modulo_id)}</b> '
            f'{html.escape(c.bloque_id)}<br>{html.escape(c.texto)}</div>')


def grilla_a_html(grilla: Grilla, compacta: bool = False) -> str:
    """Tabla HTML de la grilla (franjas en filas, días en columnas)."""
    ancho = "46px" if compacta else "92px"
    fs = "0.62rem" if compacta else "0.78rem"
    partes = [f'<table style="border-collapse:collapse;width:100%;'
              f'table-layout:fixed;font-size:{fs}">',
              "<thead><tr><th style='width:"
              + ("70px" if compacta else "110px") + "'></th>"]
    for e in grilla.etiquetas_dias:
        partes.append(
            f"<th style='border:1px solid #8886;padding:2px;"
            f"min-width:{ancho}'>{html.escape(e)}</th>")
    partes.append("</tr></thead><tbody>")
    for h, etiqueta in zip(grilla.filas, grilla.etiquetas_filas):
        partes.append(
            f"<tr><th style='border:1px solid #8886;padding:2px;"
            f"text-align:left;white-space:nowrap'>{html.escape(etiqueta)}"
            "</th>")
        for d in grilla.dias:
            bloques = grilla.celdas.get((d, h), [])
            contenido = "".join(_html_bloque(c, compacta) for c in bloques)
            partes.append(
                "<td style='border:1px solid #8886;padding:2px;"
                f"vertical-align:top;height:{'24px' if compacta else '40px'}'>"
                f"{contenido}</td>")
        partes.append("</tr>")
    partes.append("</tbody></table>")
    return "".join(partes)
