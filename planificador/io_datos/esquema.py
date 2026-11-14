"""Esquema del formato de entrada estandarizado (plantilla Excel).

Única fuente de verdad del formato. La plantilla (``plantilla.py``) se genera
a partir de este módulo y el importador lo usa para validar. Solo lo modifica
el orquestador (contrato congelado; ver ``docs/contrato.md``).

Cada hoja es una tabla simple: la fila 1 tiene los encabezados (``Columna.nombre``)
y los datos empiezan en la fila 2. En las hojas de tipo ``"grilla"`` (Disponibilidad)
cada fila es una franja de un docente y hay una columna por día.
"""

from dataclasses import dataclass, field
from typing import Optional

VERSION_ESQUEMA = "0.1"

DIAS = ("LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO")
SI_NO = ("SI", "NO")
TIPOS_FRANJA = ("CLASE", "TALLER", "RECESO")
TIPOS_DIA = ("HABIL", "FESTIVO", "VACACIONES", "SIN_CLASE")
TIPOS_SESION = ("TEORIA", "TALLER", "PRACTICA")
MODALIDADES = ("PRESENCIAL", "VIRTUAL")
JORNADAS = ("DIURNA", "NOCTURNA", "FIN_DE_SEMANA")
JORNADAS_ROTACION = ("MAÑANA", "TARDE")
# Códigos observados en el calendario de rotación actual; ampliables en v1.0.
CODIGOS_ROTACION = ("CF", "TA", "NA", "FU", "FGD", "D")


@dataclass(frozen=True)
class Columna:
    """Una columna de una hoja de la plantilla."""

    nombre: str
    tipo: str  # "texto" | "entero" | "decimal" | "fecha" | "hora" | "opcion"
    obligatoria: bool
    descripcion: str
    opciones: Optional[tuple] = None  # solo si tipo == "opcion"
    ejemplo: object = None
    referencia: Optional[str] = None  # "Hoja.columna" si es llave foránea


@dataclass(frozen=True)
class Hoja:
    """Una hoja de la plantilla."""

    nombre: str
    descripcion: str
    quien_llena: str
    columnas: tuple
    tipo: str = "tabla"  # "tabla" | "grilla"
    llave: tuple = field(default_factory=tuple)  # columnas que identifican la fila


def _c(nombre, tipo, obligatoria, descripcion, opciones=None, ejemplo=None,
       referencia=None):
    return Columna(nombre, tipo, obligatoria, descripcion, opciones, ejemplo,
                   referencia)


HOJAS = (
    Hoja(
        "Programa",
        "Datos generales del programa (una sola fila).",
        "Coordinación",
        (
            _c("nombre", "texto", True, "Nombre del programa",
               ejemplo="INVESTIGACION JUDICIAL"),
            _c("fecha_inicio", "fecha", True, "Primer día de clases",
               ejemplo="2026-02-02"),
            _c("fecha_fin", "fecha", True, "Último día de clases",
               ejemplo="2026-12-12"),
            _c("horas_totales", "entero", True, "Horas totales del programa",
               ejemplo=1800),
            _c("horas_teoricas", "entero", True, "Horas teóricas",
               ejemplo=900),
            _c("horas_practicas", "entero", True, "Horas prácticas",
               ejemplo=900),
        ),
        llave=("nombre",),
    ),
    Hoja(
        "Franjas",
        "Franjas horarias de un día tipo, en orden.",
        "Coordinación",
        (
            _c("id", "texto", True, "Identificador corto de la franja",
               ejemplo="F1"),
            _c("hora_inicio", "hora", True, "Hora de inicio (HH:MM, 24 h)",
               ejemplo="07:00"),
            _c("hora_fin", "hora", True, "Hora de fin (HH:MM, 24 h)",
               ejemplo="08:00"),
            _c("tipo", "opcion", True, "Uso de la franja", TIPOS_FRANJA,
               ejemplo="CLASE"),
        ),
        llave=("id",),
    ),
    Hoja(
        "Calendario",
        "Fechas especiales. Los días no listados se asumen hábiles.",
        "Coordinación",
        (
            _c("fecha", "fecha", True, "Fecha", ejemplo="2026-03-23"),
            _c("tipo", "opcion", True, "Tipo de día", TIPOS_DIA,
               ejemplo="FESTIVO"),
            _c("observacion", "texto", False, "Comentario libre",
               ejemplo="Día de San José"),
        ),
        llave=("fecha",),
    ),
    Hoja(
        "Docentes",
        "Lista de docentes.",
        "Coordinación",
        (
            _c("id", "texto", True, "Identificador corto del docente",
               ejemplo="D01"),
            _c("nombre", "texto", True, "Nombre completo",
               ejemplo="NOMBRE APELLIDO"),
            _c("max_horas_semana", "entero", False,
               "Máximo de horas por semana (vacío = sin límite)",
               ejemplo=20),
            _c("max_horas_dia", "entero", False,
               "Máximo de horas por día (vacío = sin límite)", ejemplo=6),
        ),
        llave=("id",),
    ),
    Hoja(
        "Modulos",
        "Módulos de la malla curricular con sus horas.",
        "Coordinación",
        (
            _c("id", "texto", True, "Identificador corto del módulo",
               ejemplo="M01"),
            _c("competencia", "texto", True, "Unidad de competencia",
               ejemplo="Estructurar hechos..."),
            _c("nombre", "texto", True, "Nombre del módulo",
               ejemplo="FOTOGRAFIA JUDICIAL"),
            _c("horas_teoria", "entero", True, "Horas de teoría", ejemplo=25),
            _c("horas_taller", "entero", True, "Horas de taller", ejemplo=5),
            _c("horas_practica", "entero", True, "Horas de práctica",
               ejemplo=12),
            _c("docente_id", "texto", False, "Docente asignado",
               referencia="Docentes.id", ejemplo="D01"),
            _c("modalidad", "opcion", True, "Presencial o virtual",
               MODALIDADES, ejemplo="PRESENCIAL"),
            _c("tipo_salon", "texto", False,
               "Tipo de salón requerido (vacío = cualquiera)",
               ejemplo="AULA"),
            _c("max_horas_seguidas", "entero", False,
               "Máximo de horas seguidas en un día", ejemplo=5),
        ),
        llave=("id",),
    ),
    Hoja(
        "Disponibilidad",
        "Disponibilidad de cada docente: una fila por docente y franja; "
        "SI/NO por día.",
        "Cada docente",
        (
            _c("docente_id", "texto", True, "Docente",
               referencia="Docentes.id", ejemplo="D01"),
            _c("franja_id", "texto", True, "Franja",
               referencia="Franjas.id", ejemplo="F1"),
        ) + tuple(
            _c(d, "opcion", True, f"¿Disponible el {d.lower()}?", SI_NO,
               ejemplo="SI")
            for d in DIAS
        ),
        tipo="grilla",
        llave=("docente_id", "franja_id"),
    ),
    Hoja(
        "Salones",
        "Salones y espacios. Los virtuales no tienen límite de capacidad.",
        "Coordinación",
        (
            _c("id", "texto", True, "Identificador corto del salón",
               ejemplo="S01"),
            _c("nombre", "texto", True, "Nombre del salón", ejemplo="Aula 101"),
            _c("sede", "texto", False, "Sede o edificio", ejemplo="Principal"),
            _c("tipo", "texto", True, "Tipo de espacio", ejemplo="AULA"),
            _c("capacidad", "entero", False,
               "Capacidad (vacío si es virtual)", ejemplo=30),
            _c("virtual", "opcion", True, "¿Es virtual?", SI_NO,
               ejemplo="NO"),
        ),
        llave=("id",),
    ),
    Hoja(
        "Grupos",
        "Grupos o cohortes que toman clase juntos.",
        "Coordinación",
        (
            _c("id", "texto", True, "Identificador del grupo", ejemplo="G1"),
            _c("programa", "texto", True, "Programa",
               ejemplo="INVESTIGACION JUDICIAL"),
            _c("cohorte", "texto", True, "Cohorte", ejemplo="2026-1"),
            _c("num_estudiantes", "entero", True, "Número de estudiantes",
               ejemplo=19),
            _c("jornada", "opcion", True, "Jornada", JORNADAS,
               ejemplo="DIURNA"),
        ),
        llave=("id",),
    ),
    Hoja(
        "Estudiantes",
        "Estudiantes (opcional si todos los del grupo ven lo mismo).",
        "Coordinación",
        (
            _c("id", "texto", True, "Identificador del estudiante",
               ejemplo="E001"),
            _c("nombre", "texto", True, "Nombre", ejemplo="NOMBRE APELLIDO"),
            _c("grupo_id", "texto", True, "Grupo", referencia="Grupos.id",
               ejemplo="G1"),
            _c("modulos", "texto", False,
               "IDs de módulos separados por coma, solo si difiere del grupo",
               ejemplo="M01,M02"),
        ),
        llave=("id",),
    ),
    Hoja(
        "Rotacion",
        "Rotación de prácticas: código por fecha y jornada.",
        "Coordinación",
        (
            _c("fecha", "fecha", True, "Fecha", ejemplo="2026-03-02"),
            _c("grupo_id", "texto", False, "Grupo (si aplica a todo el grupo)",
               referencia="Grupos.id", ejemplo="G1"),
            _c("estudiante_id", "texto", False,
               "Estudiante (si es individual)",
               referencia="Estudiantes.id", ejemplo=None),
            _c("jornada", "opcion", True, "Jornada del día", JORNADAS_ROTACION,
               ejemplo="MAÑANA"),
            _c("codigo", "opcion", True, "Código de rotación",
               CODIGOS_ROTACION, ejemplo="CF"),
            _c("lugar", "texto", False, "Lugar de práctica",
               ejemplo="CONSULTORIO JURIDICO"),
        ),
        llave=("fecha", "grupo_id", "estudiante_id", "jornada"),
    ),
)

HOJAS_POR_NOMBRE = {h.nombre: h for h in HOJAS}


def hoja(nombre: str) -> Hoja:
    """Devuelve la definición de la hoja ``nombre`` (KeyError si no existe)."""
    return HOJAS_POR_NOMBRE[nombre]
