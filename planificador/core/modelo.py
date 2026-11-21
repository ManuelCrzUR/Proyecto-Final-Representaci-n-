"""Modelo del problema: entidades de la instancia, posiciones y acciones.

CONTRATO CONGELADO (solo lo modifica el orquestador; ver ``docs/contrato.md``).

Formalización (propuesta, adaptada a franjas de duración variable):

* Tiempo: el horizonte es una secuencia de ``dias`` (índices 0..D-1) y cada día
  tiene las mismas ``franjas`` (índices 0..H-1), ordenadas y consecutivas. Los
  recesos NO son franjas: dos franjas de índices h y h+1 se consideran
  consecutivas aunque haya un receso entre ellas.
* Una celda de tiempo es el par ``(dia, franja)``.
* Un bloque ``m`` dura ``duracion`` franjas consecutivas, el mismo día y el
  mismo salón. Se ubica con una ``Posicion(dia, franja, salon)`` donde
  ``franja`` es la franja de inicio h0; ocupa h0 .. h0 + duracion - 1.
* A[t, d, h] = 1  <=>  (d, h) in docente.disponibilidad
* W[g, d, h] = 1  <=>  (d, h) in grupo.ventana   (ventana del grupo/matrícula)
* E(m) = suma de num_estudiantes de los grupos del bloque.
* Γ: dos bloques son adyacentes si comparten docente o al menos un grupo.
* Salón virtual: sin límite de capacidad ni de ocupación simultánea.

Unidad de conteo de violaciones de tiempo: la franja (no la hora de reloj).
Las horas reales de un bloque se obtienen con ``Instancia.horas_bloque``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from functools import cached_property
from typing import Optional, Union

Celda = tuple  # (dia: int, franja: int)


# --------------------------------------------------------------------------
# Entidades
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Franja:
    """Franja horaria de un día tipo. Minutos desde las 00:00."""

    id: str
    inicio: int
    fin: int
    extrema: bool = False  # True si se penaliza como "hora extrema"

    @property
    def minutos(self) -> int:
        return self.fin - self.inicio


@dataclass(frozen=True)
class Dia:
    """Día del horizonte. ``semana`` y ``dia_semana`` (0=lunes..5=sábado)."""

    indice: int
    semana: int = 0
    dia_semana: int = 0
    fecha: Optional[str] = None  # ISO AAAA-MM-DD si aplica


@dataclass(frozen=True)
class Salon:
    id: str
    tipo: str = "AULA"
    capacidad: Optional[int] = None  # None = sin límite (virtual)
    virtual: bool = False
    sede: str = ""


@dataclass(frozen=True)
class Docente:
    id: str
    nombre: str = ""
    disponibilidad: frozenset = frozenset()  # conjunto de Celda
    max_franjas_dia: Optional[int] = None


@dataclass(frozen=True)
class Grupo:
    """Conjunto de estudiantes que cursan juntos (rol de E y de k)."""

    id: str
    num_estudiantes: int = 0
    ventana: frozenset = frozenset()  # conjunto de Celda permitidas
    max_franjas_dia: Optional[int] = None


@dataclass(frozen=True)
class Bloque:
    """Sesión indivisible de un módulo (variable del problema)."""

    id: str
    modulo_id: str
    duracion: int  # δ(m) en franjas, >= 1
    grupos: tuple = ()  # ids de Grupo
    docente_id: Optional[str] = None  # None = sin docente (no genera A ni Γ)
    tipo_sesion: str = "TEORIA"  # TEORIA | TALLER | PRACTICA
    tipo_salon: Optional[str] = None  # None = cualquier tipo
    virtual: bool = False  # True = debe ir en un salón virtual
    serie: Optional[str] = None  # bloques con la misma serie comparten el tope diario
    max_franjas_dia: Optional[int] = None  # tope DURO de franjas de la serie por día (None = sin tope)


@dataclass(frozen=True)
class Pesos:
    """Pesos w_i de las penalizaciones blandas φ_i y λ.

    ``lam = None`` significa λ automático = cota_superior_f(instancia) + 1
    (lo calcula ``core.costo``).
    """

    hueco_docente: float = 1.0
    hueco_grupo: float = 1.0
    dispersion_docente: float = 1.0
    carga_grupo: float = 1.0
    hora_extrema: float = 1.0
    cambio_sede: float = 1.0
    lam: Optional[float] = None


@dataclass(frozen=True)
class Instancia:
    """Datos de entrada completos e inmutables."""

    dias: tuple
    franjas: tuple
    salones: tuple
    docentes: tuple
    grupos: tuple
    bloques: tuple
    pesos: Pesos = field(default_factory=Pesos)
    nombre: str = "instancia"

    def __post_init__(self):
        for etiqueta, coleccion in (("salones", self.salones),
                                    ("docentes", self.docentes),
                                    ("grupos", self.grupos),
                                    ("bloques", self.bloques)):
            ids = [x.id for x in coleccion]
            if len(ids) != len(set(ids)):
                raise ValueError(f"IDs repetidos en {etiqueta}")
        if [d.indice for d in self.dias] != list(range(len(self.dias))):
            raise ValueError("Los días deben tener índices 0..D-1 en orden")
        docentes = {d.id for d in self.docentes}
        grupos = {g.id for g in self.grupos}
        for b in self.bloques:
            if b.duracion < 1 or b.duracion > len(self.franjas):
                raise ValueError(f"Duración inválida en bloque {b.id}")
            if b.docente_id is not None and b.docente_id not in docentes:
                raise ValueError(f"Bloque {b.id}: docente desconocido")
            if not set(b.grupos) <= grupos:
                raise ValueError(f"Bloque {b.id}: grupo desconocido")

    # --- índices de consulta (calculados una vez) -------------------------
    @cached_property
    def salon(self) -> dict:
        return {s.id: s for s in self.salones}

    @cached_property
    def docente(self) -> dict:
        return {d.id: d for d in self.docentes}

    @cached_property
    def grupo(self) -> dict:
        return {g.id: g for g in self.grupos}

    @cached_property
    def bloque(self) -> dict:
        return {b.id: b for b in self.bloques}

    @property
    def num_dias(self) -> int:
        return len(self.dias)

    @property
    def num_franjas(self) -> int:
        return len(self.franjas)

    def estudiantes(self, bloque_id: str) -> int:
        """|E(m)|: estudiantes del bloque."""
        b = self.bloque[bloque_id]
        return sum(self.grupo[g].num_estudiantes for g in b.grupos)

    def horas_bloque(self, bloque_id: str, franja_inicio: int) -> float:
        """Horas reales de reloj de un bloque ubicado desde ``franja_inicio``."""
        b = self.bloque[bloque_id]
        fr = self.franjas[franja_inicio:franja_inicio + b.duracion]
        return sum(f.minutos for f in fr) / 60.0

    # --- serialización --------------------------------------------------
    def a_dict(self) -> dict:
        """Representación JSON-serializable (frozensets → listas ordenadas)."""
        def conv(x):
            if isinstance(x, frozenset):
                return sorted(list(c) for c in x)
            if isinstance(x, (tuple, list)):
                return [conv(i) for i in x]
            if isinstance(x, dict):
                return {k: conv(v) for k, v in x.items()}
            return x
        return conv({
            "nombre": self.nombre,
            "pesos": asdict(self.pesos),
            "dias": [asdict(d) for d in self.dias],
            "franjas": [asdict(f) for f in self.franjas],
            "salones": [asdict(s) for s in self.salones],
            "docentes": [asdict(d) for d in self.docentes],
            "grupos": [asdict(g) for g in self.grupos],
            "bloques": [asdict(b) for b in self.bloques],
        })

    @staticmethod
    def desde_dict(datos: dict) -> "Instancia":
        """Inversa de ``a_dict``."""
        def celdas(lista):
            return frozenset(tuple(c) for c in lista)
        return Instancia(
            nombre=datos.get("nombre", "instancia"),
            pesos=Pesos(**datos.get("pesos", {})),
            dias=tuple(Dia(**d) for d in datos["dias"]),
            franjas=tuple(Franja(**f) for f in datos["franjas"]),
            salones=tuple(Salon(**s) for s in datos["salones"]),
            docentes=tuple(
                Docente(**{**d, "disponibilidad": celdas(d["disponibilidad"])})
                for d in datos["docentes"]),
            grupos=tuple(
                Grupo(**{**g, "ventana": celdas(g["ventana"])})
                for g in datos["grupos"]),
            bloques=tuple(
                Bloque(**{**b, "grupos": tuple(b["grupos"])})
                for b in datos["bloques"]),
        )


# --------------------------------------------------------------------------
# Violaciones duras (compartido por costo.py y validador.py)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Violaciones:
    """Desglose de v(X) = |U| + v_disp + v_vent + v_conf (+ v_salon).

    ``salon`` cuenta celdas con dos bloques en un salón no virtual o bloques en
    salones de capacidad/tipo/modalidad inválidos; con acciones legales es 0.
    """

    sin_ubicar: int = 0
    disponibilidad: int = 0
    ventana: int = 0
    conflicto: int = 0
    salon: int = 0

    @property
    def total(self) -> int:
        return (self.sin_ubicar + self.disponibilidad + self.ventana
                + self.conflicto + self.salon)


# --------------------------------------------------------------------------
# Posiciones y acciones
# --------------------------------------------------------------------------

@dataclass(frozen=True, order=True)
class Posicion:
    """(d, h0, s): día, franja de inicio y salón."""

    dia: int
    franja: int
    salon: str


@dataclass(frozen=True)
class Anadir:
    """(add, m, d, h0, s)"""

    bloque: str
    posicion: Posicion


@dataclass(frozen=True)
class Eliminar:
    """(del, m)"""

    bloque: str


@dataclass(frozen=True)
class Intercambiar:
    """(swap, m, m'): solo bloques ubicados de igual duración."""

    bloque_a: str
    bloque_b: str


@dataclass(frozen=True)
class Reubicar:
    """(move, m, d, h0, s) = eliminar + añadir en un paso."""

    bloque: str
    posicion: Posicion


@dataclass(frozen=True)
class CambiarSalon:
    """(room, m, s): mismo día y franja, otro salón."""

    bloque: str
    salon: str


Accion = Union[Anadir, Eliminar, Intercambiar, Reubicar, CambiarSalon]


def celdas_de(posicion: Posicion, duracion: int) -> tuple:
    """Celdas (dia, franja) que ocupa un bloque de ``duracion`` en ``posicion``."""
    return tuple((posicion.dia, posicion.franja + i) for i in range(duracion))
