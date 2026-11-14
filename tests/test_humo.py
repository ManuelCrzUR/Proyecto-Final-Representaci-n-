"""Pruebas de humo: el paquete importa y el esquema es coherente."""

import planificador
from planificador.io_datos import esquema


def test_paquete_importable():
    assert planificador is not None


def test_version_esquema_es_str():
    assert isinstance(esquema.VERSION_ESQUEMA, str)


def test_hojas_no_vacias():
    assert len(esquema.HOJAS) > 0


def test_nombres_de_hoja_unicos():
    nombres = [h.nombre for h in esquema.HOJAS]
    assert len(nombres) == len(set(nombres))
