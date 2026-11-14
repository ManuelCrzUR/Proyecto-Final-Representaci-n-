# Agente planificador de horarios

Agente que genera horarios sin cruces para un programa académico, a partir de una
plantilla Excel estandarizada con programa, docentes, módulos, salones, grupos y
disponibilidad. Proyecto del curso *Representación y solución automática de
problemas*, Universidad del Rosario.

Autores: Manuel Cruz y Santiago Peña.

## Estructura

- `planificador/`: paquete principal.
  - `core/`: entidades e interfaces del núcleo.
  - `algoritmos/`: solvers que generan los horarios.
  - `io_datos/`: lectura, validación y escritura (incluye `esquema.py`, formato de entrada).
  - `experimentos/`: comparaciones y experimentos.
  - `app/`: interfaz de usuario.
- `herramientas/`: scripts auxiliares.
- `tests/`: pruebas automáticas.
- `docs/`: documentación y contrato de desarrollo.
- `salidas/`: resultados generados (no se versiona).

## Instalación

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Ejecutar pruebas

```bash
.venv/bin/pytest
```

## Uso

Pendiente.

## Capturas

Pendiente.
