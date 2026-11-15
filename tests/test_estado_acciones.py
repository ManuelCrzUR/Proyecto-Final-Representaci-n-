"""Tests de ``core/estado.py`` y ``core/acciones.py``."""

import random

import pytest

from planificador.core.acciones import (acciones_legales, aplicar,
                                        aplicar_en_sitio, es_legal,
                                        posiciones_legales)
from planificador.core.estado import Estado
from planificador.core.modelo import (Anadir, Bloque, CambiarSalon, Dia,
                                      Docente, Eliminar, Franja, Grupo,
                                      Instancia, Intercambiar, Posicion,
                                      Reubicar, Salon, celdas_de)

D, H = 2, 4


def _instancia(bloques=None) -> Instancia:
    """2 días x 4 franjas; salones normal, chico, laboratorio y virtual."""
    if bloques is None:
        bloques = (
            Bloque("b1", "m1", 1, ("g1",), "d1"),
            Bloque("b2", "m2", 2, ("g2",), "d2"),
            Bloque("b3", "m3", 1, ("g1",), "d1", tipo_salon="LAB"),
            Bloque("b4", "m4", 1, ("g2",), "d2", virtual=True),
            Bloque("b5", "m5", 1, ("g2",), "d1"),
            Bloque("b6", "m6", 2, ("g1",), "d2", virtual=True),
            Bloque("b7", "m7", 2, ("g1",), "d2"),
        )
    return Instancia(
        dias=tuple(Dia(i, 0, i) for i in range(D)),
        franjas=tuple(Franja(f"f{h}", 60 * h, 60 * h + 50) for h in range(H)),
        salones=(
            Salon("A1", "AULA", 30),
            Salon("A2", "AULA", 10),
            Salon("LAB", "LAB", 30),
            Salon("V", "VIRTUAL", None, virtual=True),
        ),
        docentes=(Docente("d1"), Docente("d2")),
        grupos=(Grupo("g1", 20), Grupo("g2", 25)),
        bloques=tuple(bloques),
    )


@pytest.fixture
def inst():
    return _instancia()


@pytest.fixture
def est(inst):
    return Estado(inst)


def P(d, h, s):
    return Posicion(d, h, s)


# --------------------------------------------------------------------------
# Estado
# --------------------------------------------------------------------------

def test_estado_vacio_y_consultas(inst, est):
    assert est.sin_ubicar() == frozenset(b.id for b in inst.bloques)
    assert est.posicion("b1") is None
    assert est.bloques_en((0, 0)) == frozenset()
    assert est.ocupante("A1", (0, 0)) is None
    assert len(est.asignacion) == 0
    assert "Estado" in repr(est)


def test_estado_inicial_indices(inst):
    e = Estado(inst, {"b2": P(0, 1, "A1"), "b4": P(0, 1, "V")})
    assert e.posicion("b2") == P(0, 1, "A1")
    assert e.sin_ubicar() == frozenset({"b1", "b3", "b5", "b6", "b7"})
    assert e.ocupante("A1", (0, 1)) == "b2"
    assert e.ocupante("A1", (0, 2)) == "b2"
    assert e.ocupante("A1", (0, 3)) is None
    assert e.ocupante("V", (0, 1)) is None  # virtual: siempre None
    assert e.bloques_en((0, 1)) == frozenset({"b2", "b4"})
    assert e.bloques_en((0, 2)) == frozenset({"b2"})
    assert e.ocupacion_docente("d2", (0, 1)) == 2
    assert e.ocupacion_docente("d2", (0, 2)) == 1
    assert e.ocupacion_grupo("g2", (0, 1)) == 2
    assert e.ocupacion_grupo("g1", (0, 1)) == 0


def test_asignacion_es_solo_lectura(est):
    with pytest.raises(TypeError):
        est.asignacion["b1"] = P(0, 0, "A1")


def test_constructor_valida_forma(inst):
    with pytest.raises(ValueError):
        Estado(inst, {"zz": P(0, 0, "A1")})
    with pytest.raises(ValueError):
        Estado(inst, {"b1": P(2, 0, "A1")})
    with pytest.raises(ValueError):
        Estado(inst, {"b1": P(0, 4, "A1")})
    with pytest.raises(ValueError):
        Estado(inst, {"b2": P(0, 3, "A1")})  # dur 2 no cabe
    with pytest.raises(ValueError):
        Estado(inst, {"b1": P(0, 0, "XX")})


def test_constructor_choque_en_salon_normal(inst):
    with pytest.raises(ValueError, match="choca"):
        Estado(inst, {"b1": P(0, 0, "A1"), "b5": P(0, 0, "A1")})
    # En virtual conviven
    Estado(inst, {"b4": P(0, 0, "V"), "b6": P(0, 0, "V")})


def test_constructor_no_exige_legalidad_de_salon(inst):
    # b1 (20 est.) en A2 (cap 10) y b3 (LAB) en A1: ilegal pero permitido.
    e = Estado(inst, {"b1": P(0, 0, "A2"), "b3": P(0, 1, "A1")})
    assert len(e.asignacion) == 2


def test_clave_eq_hash(inst):
    e1 = Estado(inst, {"b1": P(0, 0, "A1"), "b2": P(1, 0, "A2")})
    e2 = Estado(inst, {"b2": P(1, 0, "A2"), "b1": P(0, 0, "A1")})
    e3 = Estado(inst, {"b1": P(0, 0, "A1")})
    assert e1.clave() == e2.clave()
    assert e1 == e2 and hash(e1) == hash(e2)
    assert e1 != e3
    assert e1.clave() == frozenset({("b1", P(0, 0, "A1")),
                                    ("b2", P(1, 0, "A2"))})


def test_copiar_independiente(inst):
    e = Estado(inst, {"b1": P(0, 0, "A1"), "b4": P(0, 0, "V")})
    c = e.copiar()
    assert c == e and c.instancia is e.instancia
    aplicar_en_sitio(c, Eliminar("b1"))
    aplicar_en_sitio(c, Anadir("b2", P(1, 0, "A1")))
    assert e.clave() == frozenset({("b1", P(0, 0, "A1")),
                                   ("b4", P(0, 0, "V"))})
    assert e.ocupante("A1", (0, 0)) == "b1"
    assert e.bloques_en((0, 0)) == frozenset({"b1", "b4"})
    assert e.ocupante("A1", (1, 0)) is None
    assert "b1" not in e.sin_ubicar() and "b2" in e.sin_ubicar()
    assert e.ocupacion_docente("d1", (0, 0)) == 1
    # y a la inversa
    aplicar_en_sitio(e, Eliminar("b4"))
    assert c.posicion("b4") == P(0, 0, "V")
    assert c.bloques_en((0, 0)) == frozenset({"b4"})


# --------------------------------------------------------------------------
# Legalidad
# --------------------------------------------------------------------------

def test_legal_anadir(inst, est):
    assert es_legal(est, Anadir("b1", P(0, 0, "A1")))
    # forma
    assert not es_legal(est, Anadir("b1", P(2, 0, "A1")))
    assert not es_legal(est, Anadir("b1", P(-1, 0, "A1")))
    assert not es_legal(est, Anadir("b1", P(0, 4, "A1")))
    assert not es_legal(est, Anadir("b2", P(0, 3, "A1")))
    assert es_legal(est, Anadir("b2", P(0, 2, "A1")))
    # capacidad (b5: 25 est.) y tipo
    assert not es_legal(est, Anadir("b5", P(0, 0, "A2")))
    assert not es_legal(est, Anadir("b1", P(0, 0, "A2")))  # 20 > 10
    assert not es_legal(est, Anadir("b3", P(0, 0, "A1")))  # b3 exige LAB
    assert es_legal(est, Anadir("b3", P(0, 0, "LAB")))
    # modalidad
    assert not es_legal(est, Anadir("b1", P(0, 0, "V")))
    assert not es_legal(est, Anadir("b4", P(0, 0, "A1")))
    assert es_legal(est, Anadir("b4", P(0, 0, "V")))
    # desconocidos
    assert not es_legal(est, Anadir("zz", P(0, 0, "A1")))
    assert not es_legal(est, Anadir("b1", P(0, 0, "XX")))


def test_legal_anadir_requiere_sin_ubicar(inst):
    e = Estado(inst, {"b1": P(0, 0, "A1")})
    assert not es_legal(e, Anadir("b1", P(1, 0, "A1")))


def test_legal_anadir_celdas_libres(inst):
    e = Estado(inst, {"b2": P(0, 1, "A1")})  # ocupa franjas 1 y 2
    assert not es_legal(e, Anadir("b1", P(0, 1, "A1")))
    assert not es_legal(e, Anadir("b1", P(0, 2, "A1")))
    assert es_legal(e, Anadir("b1", P(0, 3, "A1")))
    assert es_legal(e, Anadir("b1", P(1, 1, "A1")))
    assert not es_legal(e, Anadir("b7", P(0, 0, "A1")))  # traslapa f1
    assert es_legal(e, Anadir("b7", P(1, 0, "A1")))


def test_virtual_simultaneos_si_normal_no(inst):
    e = Estado(inst, {"b4": P(0, 0, "V")})
    assert es_legal(e, Anadir("b6", P(0, 0, "V")))
    e = aplicar(e, Anadir("b6", P(0, 0, "V")))
    assert e.bloques_en((0, 0)) == frozenset({"b4", "b6"})
    e2 = Estado(inst, {"b1": P(0, 0, "A1")})
    assert not es_legal(e2, Anadir("b5", P(0, 0, "A1")))
    assert es_legal(e2, Anadir("b7", P(0, 1, "A1")))


def test_legal_eliminar(inst):
    e = Estado(inst, {"b1": P(0, 0, "A1")})
    assert es_legal(e, Eliminar("b1"))
    assert not es_legal(e, Eliminar("b5"))  # sin ubicar
    assert not es_legal(e, Eliminar("zz"))


def test_legal_reubicar(inst):
    e = Estado(inst, {"b2": P(0, 0, "A1"), "b1": P(1, 0, "A1")})
    # se ignora a sí mismo: desplazar b2 a (0,1) solapa sus propias celdas
    assert es_legal(e, Reubicar("b2", P(0, 1, "A1")))
    assert es_legal(e, Reubicar("b2", P(0, 0, "A1")))  # no-op legal
    # ocupado por otro
    assert not es_legal(e, Reubicar("b2", P(1, 0, "A1")))
    assert not es_legal(e, Reubicar("b1", P(0, 1, "A1")))
    # forma, salón, modalidad
    assert not es_legal(e, Reubicar("b2", P(0, 3, "A1")))
    assert not es_legal(e, Reubicar("b1", P(0, 0, "A2")))
    assert not es_legal(e, Reubicar("b1", P(0, 0, "V")))
    # no ubicado
    assert not es_legal(e, Reubicar("b5", P(0, 0, "A1")))


def test_legal_cambiar_salon(inst):
    e = Estado(inst, {"b1": P(0, 0, "A1"), "b3": P(0, 1, "LAB"),
                      "b5": P(0, 0, "LAB"), "b4": P(0, 0, "V")})
    assert es_legal(e, CambiarSalon("b5", "A1")) is False  # A1 ocupado
    assert not es_legal(e, CambiarSalon("b1", "A2"))  # capacidad
    assert es_legal(e, CambiarSalon("b1", "LAB")) is False  # LAB ocupado
    e = Estado(inst, {"b1": P(0, 0, "A1")})
    assert es_legal(e, CambiarSalon("b1", "LAB"))
    assert not es_legal(e, CambiarSalon("b1", "A2"))  # capacidad
    assert not es_legal(e, CambiarSalon("b1", "V"))  # modalidad
    assert not es_legal(e, CambiarSalon("b1", "XX"))
    assert not es_legal(e, CambiarSalon("b5", "A1"))  # no ubicado
    e = Estado(inst, {"b3": P(0, 0, "LAB")})
    assert not es_legal(e, CambiarSalon("b3", "A1"))  # tipo
    e = Estado(inst, {"b4": P(0, 0, "V")})
    assert not es_legal(e, CambiarSalon("b4", "A1"))  # virtual -> normal


def test_legal_intercambiar(inst):
    e = Estado(inst, {"b1": P(0, 0, "A1"), "b5": P(1, 2, "LAB"),
                      "b2": P(0, 1, "A1"), "b3": P(1, 0, "LAB"),
                      "b7": P(1, 2, "A1")})
    assert es_legal(e, Intercambiar("b1", "b5"))
    assert es_legal(e, Intercambiar("b2", "b7"))
    # duraciones distintas
    assert not es_legal(e, Intercambiar("b1", "b2"))
    # b3 exige LAB: no puede ir a A1
    assert not es_legal(e, Intercambiar("b1", "b3"))
    # no ubicado y mismo bloque
    assert not es_legal(e, Intercambiar("b1", "b4"))
    assert not es_legal(e, Intercambiar("b1", "b1"))
    e = Estado(inst, {"b1": P(0, 0, "A1"), "b5": P(0, 1, "A1")})
    assert es_legal(e, Intercambiar("b1", "b5"))
    # virtual con normal nunca
    e = Estado(inst, {"b4": P(0, 0, "V"), "b5": P(0, 0, "A1")})
    assert not es_legal(e, Intercambiar("b4", "b5"))


def test_intercambiar_ignora_ambos_bloques(inst):
    # b2 y b7 (dur 2) solapados por intercambio en el mismo salón:
    # b2 en (0,0)-(0,1); b7 en (0,1)? chocaría; usar contiguos.
    e = Estado(inst, {"b2": P(0, 0, "A1"), "b7": P(0, 2, "A1")})
    assert es_legal(e, Intercambiar("b2", "b7"))
    r = aplicar(e, Intercambiar("b2", "b7"))
    assert r.posicion("b2") == P(0, 2, "A1")
    assert r.posicion("b7") == P(0, 0, "A1")


# --------------------------------------------------------------------------
# aplicar / en sitio / inversas
# --------------------------------------------------------------------------

def test_aplicar_es_pura_y_lanza_si_ilegal(inst):
    e = Estado(inst, {"b1": P(0, 0, "A1")})
    antes = e.clave()
    n = aplicar(e, Anadir("b5", P(0, 1, "A1")))
    assert e.clave() == antes
    assert n.posicion("b5") == P(0, 1, "A1")
    with pytest.raises(ValueError):
        aplicar(e, Anadir("b5", P(0, 0, "A1")))
    with pytest.raises(ValueError):
        aplicar_en_sitio(e, Anadir("b5", P(0, 0, "A1")))
    assert e.clave() == antes


@pytest.mark.parametrize("accion", [
    Anadir("b7", P(1, 2, "A1")),
    Eliminar("b2"),
    Intercambiar("b1", "b5"),
    Reubicar("b2", P(1, 1, "A1")),
    Reubicar("b4", P(1, 3, "V")),
    CambiarSalon("b1", "LAB"),
])
def test_en_sitio_e_inversa_restauran(inst, accion):
    e = Estado(inst, {"b1": P(0, 0, "A1"), "b2": P(0, 1, "A1"),
                      "b5": P(0, 3, "A1"), "b4": P(0, 0, "V")})
    antes = e.clave()
    copia = e.copiar()
    inversa = aplicar_en_sitio(e, accion)
    assert e.clave() != antes
    aplicar_en_sitio(e, inversa)
    assert e.clave() == antes
    assert e == copia
    # índices coherentes tras deshacer
    assert Estado(inst, dict(e.asignacion)).clave() == antes
    for c in [(d, h) for d in range(D) for h in range(H)]:
        assert e.bloques_en(c) == copia.bloques_en(c)
        for s in ("A1", "A2", "LAB", "V"):
            assert e.ocupante(s, c) == copia.ocupante(s, c)


def test_tipos_de_inversa(inst):
    e = Estado(inst, {"b1": P(0, 0, "A1"), "b2": P(0, 1, "A1")})
    assert aplicar_en_sitio(e, Anadir("b5", P(1, 0, "A1"))) == Eliminar("b5")
    assert aplicar_en_sitio(e, Eliminar("b5")) == Anadir("b5", P(1, 0, "A1"))
    assert aplicar_en_sitio(e, Reubicar("b1", P(1, 2, "A1"))) == \
        Reubicar("b1", P(0, 0, "A1"))
    assert aplicar_en_sitio(e, CambiarSalon("b1", "LAB")) == \
        CambiarSalon("b1", "A1")
    assert not es_legal(e, Intercambiar("b1", "b1"))


# --------------------------------------------------------------------------
# Generadores
# --------------------------------------------------------------------------

def _todas_las_posiciones(inst, bid):
    return [P(d, h, s.id)
            for d in range(-1, D + 1)
            for h in range(-1, H + 1)
            for s in sorted(inst.salones, key=lambda s: s.id)]


def test_posiciones_legales_orden_y_filtrado(inst):
    e = Estado(inst, {"b2": P(0, 1, "A1"), "b4": P(1, 0, "V"),
                      "b1": P(1, 2, "LAB")})
    for b in inst.bloques:
        legales = posiciones_legales(e, b.id)
        assert legales == sorted(legales)  # (dia, franja, salon)
        assert legales == posiciones_legales(e, b.id)
        esperado = []
        for p in _todas_las_posiciones(inst, b.id):
            if e.posicion(b.id) is None and es_legal(e, Anadir(b.id, p)):
                esperado.append(p)
        if e.posicion(b.id) is None:
            assert legales == esperado
        else:
            # Ubicado: se ignora a sí mismo; coincide con Reubicar legal.
            assert legales == [p for p in _todas_las_posiciones(inst, b.id)
                               if es_legal(e, Reubicar(b.id, p))]


def test_posiciones_legales_ejemplo(inst):
    e = Estado(inst, {"b2": P(0, 0, "A1")})
    pos = posiciones_legales(e, "b1")
    assert P(0, 0, "A1") not in pos and P(0, 1, "A1") not in pos
    assert P(0, 2, "A1") in pos
    assert P(0, 0, "LAB") in pos
    assert all(p.salon != "V" and p.salon != "A2" for p in pos)
    assert posiciones_legales(e, "b4") == [
        P(d, h, "V") for d in range(D) for h in range(H)]


def test_acciones_legales_legales_y_sin_duplicados(inst):
    e = Estado(inst, {"b1": P(0, 0, "A1"), "b5": P(0, 1, "A1"),
                      "b4": P(0, 0, "V"), "b2": P(1, 0, "LAB"),
                      "b7": P(1, 2, "A1")})
    acciones = list(acciones_legales(e))
    assert acciones
    assert len(acciones) == len(set(acciones))
    assert all(es_legal(e, a) for a in acciones)
    assert acciones == list(acciones_legales(e))  # determinista
    tipos = {type(a) for a in acciones}
    assert tipos == {Anadir, Eliminar, Reubicar, CambiarSalon, Intercambiar}
    # Reubicar nunca a la posición actual
    for a in acciones:
        if isinstance(a, Reubicar):
            assert a.posicion != e.posicion(a.bloque)
        if isinstance(a, CambiarSalon):
            assert a.salon != e.posicion(a.bloque).salon
        if isinstance(a, Intercambiar):
            assert a.bloque_a < a.bloque_b


def test_acciones_legales_completitud(inst):
    """Todo lo legal (de un universo exhaustivo) aparece generado."""
    e = Estado(inst, {"b1": P(0, 0, "A1"), "b5": P(0, 1, "A1"),
                      "b4": P(0, 0, "V"), "b2": P(1, 0, "LAB")})
    gen = set(acciones_legales(e))
    universo = set()
    for b in inst.bloques:
        for p in _todas_las_posiciones(inst, b.id):
            universo.add(Anadir(b.id, p))
            universo.add(Reubicar(b.id, p))
        universo.add(Eliminar(b.id))
        for s in inst.salones:
            universo.add(CambiarSalon(b.id, s.id))
        for o in inst.bloques:
            if b.id < o.id:
                universo.add(Intercambiar(b.id, o.id))
    legales = {a for a in universo if es_legal(e, a)}
    # Los no-op quedan fuera del generador por diseño.
    legales = {a for a in legales
               if not (isinstance(a, Reubicar)
                       and a.posicion == e.posicion(a.bloque))
               and not (isinstance(a, CambiarSalon)
                        and a.salon == e.posicion(a.bloque).salon)}
    assert gen == legales


def test_acciones_legales_es_generador(est):
    import types
    assert isinstance(acciones_legales(est), types.GeneratorType)


# --------------------------------------------------------------------------
# Propiedad aleatoria
# --------------------------------------------------------------------------

def _consistente(e: Estado):
    inst = e.instancia
    ref = Estado(inst, dict(e.asignacion))
    assert e.clave() == ref.clave()
    assert e.sin_ubicar() == ref.sin_ubicar()
    assert e.sin_ubicar() == frozenset(
        b.id for b in inst.bloques if b.id not in e.asignacion)
    for d in range(D):
        for h in range(H):
            c = (d, h)
            esperado = frozenset(
                b for b, p in e.asignacion.items()
                if c in celdas_de(p, inst.bloque[b].duracion))
            assert e.bloques_en(c) == esperado == ref.bloques_en(c)
            for s in inst.salones:
                o = e.ocupante(s.id, c)
                assert o == ref.ocupante(s.id, c)
                if s.virtual:
                    assert o is None
                else:
                    assert o in {b for b in esperado
                                 if e.posicion(b).salon == s.id} | {None}
                    assert (o is None) == all(
                        e.posicion(b).salon != s.id for b in esperado)
            for doc in inst.docentes:
                n = sum(1 for b in esperado
                        if inst.bloque[b].docente_id == doc.id)
                assert e.ocupacion_docente(doc.id, c) == n
                assert ref.ocupacion_docente(doc.id, c) == n
            for g in inst.grupos:
                n = sum(1 for b in esperado if g.id in inst.bloque[b].grupos)
                assert e.ocupacion_grupo(g.id, c) == n
                assert ref.ocupacion_grupo(g.id, c) == n


def test_propiedad_aleatoria_indices_consistentes(inst):
    rng = random.Random(12345)
    e = Estado(inst)
    historial = []
    for paso in range(500):
        acciones = list(acciones_legales(e))
        a = rng.choice(acciones)
        antes = e.clave()
        pura = aplicar(e, a)
        assert e.clave() == antes
        inversa = aplicar_en_sitio(e, a)
        assert e == pura
        historial.append((antes, inversa))
        _consistente(e)
        if rng.random() < 0.2:  # deshacer a veces
            antes, inv = historial.pop()
            aplicar_en_sitio(e, inv)
            assert e.clave() == antes
            _consistente(e)
    # Nunca hay choques en salón no virtual ni salones inválidos
    for b, p in e.asignacion.items():
        bl = inst.bloque[b]
        s = inst.salon[p.salon]
        assert bl.virtual == s.virtual
        if not s.virtual:
            assert bl.tipo_salon in (None, s.tipo)
            assert s.capacidad >= inst.estudiantes(b)
