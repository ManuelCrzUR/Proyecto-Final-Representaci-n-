"""Tests de conflictos y costo con casos pequeños calculados a mano.

Instancia base: D=2 días, H=4 franjas (0 y 3 extremas), salones S1 (AULA,
cap 30, sede A), S2 (AULA, cap 30, sede B), LAB (LAB, cap 10, sede A) y V
(virtual). Docentes T1, T2 con disponibilidad total; grupos G1, G2 (20
estudiantes, ventana total).
"""

from types import SimpleNamespace

import pytest

from planificador.core import costo
from planificador.core.conflictos import construir_conflictos, grado
from planificador.core.modelo import (
    Bloque, Dia, Docente, Franja, Grupo, Instancia, Pesos, Posicion, Salon,
    Violaciones)


def P(dia, franja, salon):
    return Posicion(dia, franja, salon)


def B(id, dur=1, grupos=("G1",), docente="T1", **kw):
    return Bloque(id, "M" + id, dur, tuple(grupos), docente, **kw)


def crear(bloques, *, dias=2, docentes=None, grupos=None, salones=None,
          pesos=None):
    franjas = tuple(Franja(f"F{h}", 480 + 60 * h, 540 + 60 * h,
                           extrema=h in (0, 3)) for h in range(4))
    todas = frozenset((d, h) for d in range(dias) for h in range(4))
    if docentes is None:
        docentes = (Docente("T1", disponibilidad=todas),
                    Docente("T2", disponibilidad=todas))
    if grupos is None:
        grupos = (Grupo("G1", 20, todas), Grupo("G2", 20, todas))
    if salones is None:
        salones = (Salon("S1", "AULA", 30, False, "A"),
                   Salon("S2", "AULA", 30, False, "B"),
                   Salon("LAB", "LAB", 10, False, "A"),
                   Salon("V", "VIRTUAL", None, True, ""))
    return Instancia(
        dias=tuple(Dia(i) for i in range(dias)), franjas=franjas,
        salones=salones, docentes=tuple(docentes), grupos=tuple(grupos),
        bloques=tuple(bloques), pesos=pesos or Pesos(lam=100.0))


def estado(inst, asig):
    """Stub mínimo de Estado: solo .instancia y .asignacion."""
    return SimpleNamespace(instancia=inst, asignacion=asig)


def viol(inst, asig):
    return costo.violaciones(estado(inst, asig))


# --------------------------------------------------------------------------
# Escenarios (compartidos con test_validador): nombre -> (inst, asig)
# --------------------------------------------------------------------------

def esc_sin_ubicar():
    inst = crear([B("B1"), B("B2", docente="T2"), B("B3", grupos=("G2",))])
    return inst, {"B1": P(0, 0, "S1")}


def esc_disponibilidad():
    dispo = frozenset({(0, 0), (0, 1)})
    docentes = (Docente("T1", disponibilidad=dispo),
                Docente("T2", disponibilidad=dispo))
    inst = crear([B("B1", 2), B("B2", 1, ("G2",), None)], docentes=docentes)
    # B1 en (0,1),(0,2): (0,2) no disponible. B2 sin docente: no cuenta.
    return inst, {"B1": P(0, 1, "S1"), "B2": P(1, 3, "S2")}


def esc_ventana_dos_grupos():
    todas = frozenset((d, h) for d in range(2) for h in range(4))
    grupos = (Grupo("G1", 10, frozenset({(1, 0)})),
              Grupo("G2", 10, frozenset({(0, 0)})))
    inst = crear([B("B1", 2, ("G1", "G2"))], grupos=grupos,
                 docentes=(Docente("T1", disponibilidad=todas),))
    # Celdas (1,0),(1,1). G1: (1,1) fuera -> 1. G2: ambas fuera -> 2.
    return inst, {"B1": P(1, 0, "S1")}


def esc_conflicto_docente():
    inst = crear([B("B1", 2, ("G1",), "T1"), B("B2", 2, ("G2",), "T1")])
    # Celdas B1: (0,0),(0,1); B2: (0,1),(0,2) -> comparten (0,1).
    return inst, {"B1": P(0, 0, "S1"), "B2": P(0, 1, "S2")}


def esc_conflicto_grupo():
    inst = crear([B("B1", 1, ("G1",), "T1"), B("B2", 1, ("G1",), "T2")])
    return inst, {"B1": P(0, 1, "S1"), "B2": P(0, 1, "S2")}


def esc_sin_docente():
    inst = crear([B("B1", 1, ("G1",), None), B("B2", 1, ("G2",), None)])
    # Sin docente ni grupo común: sin conflicto (salones distintos).
    return inst, {"B1": P(0, 1, "S1"), "B2": P(0, 1, "S2")}


def esc_virtual_simultaneo():
    inst = crear([B("B1", 1, ("G1",), "T1", virtual=True),
                  B("B2", 1, ("G2",), "T2", virtual=True)])
    return inst, {"B1": P(0, 1, "V"), "B2": P(0, 1, "V")}


def esc_salon_choque():
    # Tres bloques en S1 en la celda (0,1): k=3 -> 2. B4 comparte (0,2)
    # con B1 (dur 2 desde (0,1)) -> +1. Total salon = 3.
    inst = crear([B("B1", 2, ("G1",), "T1"), B("B2", 1, ("G2",), "T2"),
                  B("B3", 1, (), None), B("B4", 1, (), None)])
    return inst, {"B1": P(0, 1, "S1"), "B2": P(0, 1, "S1"),
                  "B3": P(0, 1, "S1"), "B4": P(0, 2, "S1")}


def esc_salon_invalido():
    grupos = (Grupo("G1", 40, frozenset((d, h) for d in range(2)
                                        for h in range(4))),
              Grupo("G2", 5, frozenset((d, h) for d in range(2)
                                       for h in range(4))))
    inst = crear([
        B("B1", 1, ("G1",), None),                          # cap 30 < 40
        B("B2", 1, ("G2",), None, tipo_salon="LAB"),        # tipo: S1 AULA
        B("B3", 1, ("G2",), None, virtual=True),            # virtual en S2
        B("B4", 1, ("G2",), None),                          # presencial en V
        B("B5", 1, ("G2",), None),                          # salón no existe
        B("B6", 1, ("G2",), None, tipo_salon="LAB"),        # válido en LAB
    ], grupos=grupos)
    return inst, {"B1": P(0, 0, "S1"), "B2": P(0, 1, "S1"),
                  "B3": P(1, 0, "S2"), "B4": P(1, 1, "V"),
                  "B5": P(1, 2, "XX"), "B6": P(1, 3, "LAB")}


def esc_fuera_de_rango():
    inst = crear([B("B1", 2, ("G1",), "T1"), B("B2", 1, ("G2",), "T2")])
    # B1 desde franja 3 con dur 2 -> (0,3),(0,4); B2 en día 5.
    return inst, {"B1": P(0, 3, "S1"), "B2": P(5, 0, "S1")}


def esc_huecos():
    inst = crear([B("B1", 1, ("G1",), "T1"), B("B2", 1, ("G2",), "T1"),
                  B("B3", 1, ("G1",), "T2")])
    return inst, {"B1": P(0, 0, "S1"), "B2": P(0, 3, "S1"),
                  "B3": P(0, 2, "S2")}


def esc_dispersion():
    inst = crear([B(f"B{i}", 1, ("G1",), "T1") for i in range(1, 6)],
                 dias=3)
    return inst, {"B1": P(0, 0, "S1"), "B2": P(1, 0, "S1"),
                  "B3": P(2, 0, "S1"), "B4": P(0, 1, "S1"),
                  "B5": P(0, 2, "S1")}


def esc_carga():
    todas = frozenset((d, h) for d in range(2) for h in range(4))
    docentes = (Docente("T1", disponibilidad=todas, max_franjas_dia=1),
                Docente("T2", disponibilidad=todas))
    grupos = (Grupo("G1", 20, todas, max_franjas_dia=2),
              Grupo("G2", 20, todas))
    inst = crear([B("B1", 3, ("G1",), "T1"), B("B2", 1, ("G1",), "T2")],
                 docentes=docentes, grupos=grupos)
    return inst, {"B1": P(0, 0, "S1"), "B2": P(1, 0, "S1")}


def esc_extrema():
    inst = crear([B("B1", 4, ("G1",), "T1"), B("B2", 1, ("G2",), "T2"),
                  B("B3", 1, ("G2",), "T1")])
    return inst, {"B1": P(0, 0, "S1"), "B2": P(1, 1, "S1"),
                  "B3": P(1, 3, "S2")}


def esc_hueco_grupo_doble():
    inst = crear([B("B1", 1, ("G1", "G2"), "T1"), B("B2", 1, ("G1",), "T2")])
    return inst, {"B1": P(0, 0, "S1"), "B2": P(0, 2, "S1")}


def esc_cambio_sede():
    inst = crear([B("B1", 1, ("G1",), "T1"), B("B2", 1, ("G1",), "T2"),
                  B("B3", 1, ("G1",), None, virtual=True),
                  B("B4", 1, ("G1",), None), B("B5", 1, ("G1",), None)])
    return inst, {"B1": P(0, 0, "S1"), "B2": P(0, 1, "S2"),
                  "B3": P(0, 2, "V"), "B4": P(0, 3, "S1"),
                  "B5": P(1, 0, "S1")}


def esc_mixto():
    pesos = Pesos(hueco_docente=1.5, hueco_grupo=1.0, dispersion_docente=1.0,
                  carga_grupo=1.0, hora_extrema=4.0, cambio_sede=1.0,
                  lam=100.0)
    inst = crear([B("B1", 1, ("G1",), "T1"), B("B2", 1, ("G2",), "T1"),
                  B("B3", 1, ("G1",), "T2")], pesos=pesos)
    return inst, {"B1": P(0, 0, "S1"), "B2": P(0, 3, "S1")}


ESCENARIOS = {
    nombre[4:]: fn for nombre, fn in list(globals().items())
    if nombre.startswith("esc_")
}


# --------------------------------------------------------------------------
# Γ
# --------------------------------------------------------------------------

def test_conflictos_gamma_y_simetria():
    todas = frozenset({(0, 0)})
    grupos = tuple(Grupo(f"G{i}", 10, todas) for i in range(1, 5))
    docentes = (Docente("T1", disponibilidad=todas),
                Docente("T2", disponibilidad=todas))
    inst = crear([B("B1", 1, ("G1",), "T1"), B("B2", 1, ("G2",), "T1"),
                  B("B3", 1, ("G1",), "T2"), B("B4", 1, ("G3",), "T2"),
                  B("B5", 1, ("G3",), None), B("B6", 1, ("G4",), None),
                  B("B7", 1, ("G4",), None), B("B8", 1, (), None)],
                 grupos=grupos, docentes=docentes)
    gam = construir_conflictos(inst)
    esperado = {
        "B1": {"B2", "B3"}, "B2": {"B1"}, "B3": {"B1", "B4"},
        "B4": {"B3", "B5"}, "B5": {"B4"}, "B6": {"B7"}, "B7": {"B6"},
        "B8": set(),
    }
    assert {k: set(x) for k, x in gam.items()} == esperado
    for m, vecinos in gam.items():
        assert m not in vecinos
        assert all(m in gam[n] for n in vecinos)
    assert grado(gam, "B1") == 2 and grado(gam, "B8") == 0
    assert isinstance(gam["B1"], frozenset)


# --------------------------------------------------------------------------
# Violaciones
# --------------------------------------------------------------------------

def test_sin_ubicar():
    assert viol(*ESCENARIOS["sin_ubicar"]()) == Violaciones(sin_ubicar=2)


def test_disponibilidad_y_docente_none():
    assert viol(*ESCENARIOS["disponibilidad"]()) == Violaciones(
        disponibilidad=1)


def test_ventana_con_dos_grupos():
    assert viol(*ESCENARIOS["ventana_dos_grupos"]()) == Violaciones(ventana=3)


def test_conflicto_por_docente():
    assert viol(*ESCENARIOS["conflicto_docente"]()) == Violaciones(
        conflicto=1)


def test_conflicto_por_grupo_compartido():
    assert viol(*ESCENARIOS["conflicto_grupo"]()) == Violaciones(conflicto=1)


def test_sin_docente_no_genera_conflicto():
    assert viol(*ESCENARIOS["sin_docente"]()) == Violaciones()


def test_virtual_simultaneo_sin_violacion_de_salon():
    assert viol(*ESCENARIOS["virtual_simultaneo"]()) == Violaciones()


def test_virtual_con_conflicto_de_docente_si_comparte():
    inst, asig = ESCENARIOS["virtual_simultaneo"]()
    inst = crear([B("B1", 1, ("G1",), "T1", virtual=True),
                  B("B2", 1, ("G2",), "T1", virtual=True)])
    assert viol(inst, asig) == Violaciones(conflicto=1)


def test_salon_choques():
    assert viol(*ESCENARIOS["salon_choque"]()) == Violaciones(salon=3)


def test_salon_invalido_cada_causa_una_vez():
    # B1 capacidad, B2 tipo, B3 virtual en presencial, B4 presencial en
    # virtual, B5 inexistente; B6 válido. Además B1,B2,B3.. no chocan.
    assert viol(*ESCENARIOS["salon_invalido"]()) == Violaciones(salon=5)


def test_fuera_de_rango_cuenta_salon():
    # Ambos bloques fuera de rango: salon=2. B1 ocupa (0,3),(0,4): (0,4)
    # fuera de disponibilidad y ventana -> +1, +1. B2 en (5,0): +1, +1.
    assert viol(*ESCENARIOS["fuera_de_rango"]()) == Violaciones(
        disponibilidad=2, ventana=2, salon=2)


def test_v_total():
    inst, asig = ESCENARIOS["salon_choque"]()
    assert costo.v(estado(inst, asig)) == 3


# --------------------------------------------------------------------------
# f
# --------------------------------------------------------------------------

def phi(nombre):
    inst, asig = ESCENARIOS[nombre]()
    return costo.desglose_f(estado(inst, asig))


def test_desglose_claves():
    d = phi("huecos")
    assert set(d) == {"hueco_docente", "hueco_grupo", "dispersion_docente",
                      "carga_grupo", "hora_extrema", "cambio_sede"}


def test_huecos():
    d = phi("huecos")
    # T1: franjas 0 y 3 -> 4-2=2. G1: B1 (0), B3 (2) -> 1. G2: una -> 0.
    # Extremas: B1 (0) y B2 (3) -> 2. Sedes: G1 B1 S1(A), B3 S2(B) -> 1.
    assert d["hueco_docente"] == 2
    assert d["hueco_grupo"] == 1
    assert d["dispersion_docente"] == 0
    assert d["carga_grupo"] == 0
    assert d["hora_extrema"] == 2
    assert d["cambio_sede"] == 1


def test_dispersion():
    d = phi("dispersion")
    # T1: 5 franjas distintas, ceil(5/4)=2, 3 días -> 1.
    assert d["dispersion_docente"] == 1
    # Hueco docente día 0: franjas {0,1,2} sin hueco.
    assert d["hueco_docente"] == 0


def test_dispersion_sin_exceso():
    inst, asig = ESCENARIOS["dispersion"]()
    del asig["B5"]
    # 4 franjas, ceil(4/4)=1, 3 días -> 2.
    assert costo.desglose_f(estado(inst, asig))["dispersion_docente"] == 2


def test_carga():
    # G1 (max 2): día 0 con 3 franjas -> 1; día 1: 1 -> 0.
    # T1 (max 1): día 0 con 3 franjas -> 2. Total 3.
    assert phi("carga")["carga_grupo"] == 3


def test_hora_extrema():
    # B1 dur 4: franjas 0 y 3 -> 2; B2 en franja 1 -> 0; B3 en 3 -> 1.
    assert phi("extrema")["hora_extrema"] == 3


def test_hueco_grupo_con_dos_grupos():
    d = phi("hueco_grupo_doble")
    # G1: {0,2} -> 1. G2: {0} -> 0. T1: {0}; T2: {2}.
    assert d["hueco_grupo"] == 1
    assert d["hueco_docente"] == 0


def test_cambio_sede():
    # G1 día 0, no virtuales por franja: B1 A, B2 B, B4 A -> 2 cambios.
    # B3 (virtual) se ignora. Día 1: B5 solo.
    assert phi("cambio_sede")["cambio_sede"] == 2


def test_f_ponderada():
    inst, asig = ESCENARIOS["mixto"]()
    # hueco_docente=2 (w 1.5) y hora_extrema=2 (w 4): 3 + 8 = 11.
    assert costo.f(estado(inst, asig)) == pytest.approx(11.0)


# --------------------------------------------------------------------------
# Cota, lam, F y recompensa
# --------------------------------------------------------------------------

def test_cota_superior_f_valor_a_mano():
    inst, _ = ESCENARIOS["mixto"]()
    # 1.5*2*2*4 + 1*2*2*4 + 1*2*2 + 1*(2+2)*2*4 + 4*3 + 1*3
    # = 24 + 16 + 4 + 32 + 12 + 3 = 91
    assert costo.cota_superior_f(inst) == pytest.approx(91.0)


def test_lam_fijo_y_automatico():
    inst, _ = ESCENARIOS["mixto"]()
    assert costo.lam(inst) == 100.0
    auto = crear(list(inst.bloques), pesos=Pesos(
        hueco_docente=1.5, hora_extrema=4.0))
    assert costo.lam(auto) == pytest.approx(92.0)


def test_F_con_lam_fijo_y_automatico():
    inst, asig = ESCENARIOS["mixto"]()
    # v = 1 (B3 sin ubicar); f = 11.
    assert costo.v(estado(inst, asig)) == 1
    assert costo.F(estado(inst, asig)) == pytest.approx(11 + 100 * 1)
    auto = crear(list(inst.bloques),
                 pesos=Pesos(hueco_docente=1.5, hora_extrema=4.0))
    assert costo.F(estado(auto, asig)) == pytest.approx(11 + 92 * 1)


def test_recompensa():
    inst, asig = ESCENARIOS["mixto"]()
    antes = estado(inst, dict(asig))
    despues_asig = dict(asig)
    despues_asig["B3"] = P(1, 1, "S1")
    despues = estado(inst, despues_asig)
    # Después: v=0, f=11 (B3 en día 1 franja 1, no extrema, sin huecos).
    assert costo.F(despues) == pytest.approx(11.0)
    assert costo.recompensa(antes, despues) == pytest.approx(100.0)
    assert costo.recompensa(despues, antes) == pytest.approx(-100.0)


def test_cota_es_cota_en_escenarios():
    for fn in ESCENARIOS.values():
        inst, asig = fn()
        assert costo.f(estado(inst, asig)) <= costo.cota_superior_f(inst)
