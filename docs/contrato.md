# Contrato de desarrollo

Reglas que siguen el orquestador y todos los agentes. Plan completo: sprints y olas.

## Reglas

1. **Git prohibido para agentes y orquestador.** No se ejecuta `git` (commit, add, push, init, worktree…). El orquestador sugiere los commits y Manuel los ejecuta.
2. **`data exp/` es de solo lectura.** Las salidas generadas van a `salidas/`, que se ignora en git.
3. **Un dueño por archivo y por ola.** Solo se editan los archivos asignados. Si hace falta cambiar otro, se reporta.
4. **Contratos congelados**, que solo edita el orquestador:
   - `planificador/io_datos/esquema.py`: formato de entrada.
   - `planificador/core/modelo.py`: entidades e interfaces del core (sprint 2).
   - `planificador/algoritmos/base.py`: interfaz Solver, Resultado y Traza (sprint 3).
   - `docs/contrato.md`
5. **Compuerta por ola:** `pytest` en verde, `flake8` limpio, revisión del orquestador y commit de Manuel.
6. **Entrega de cada agente:** archivos creados o modificados, resultado de los tests y dudas.

## Convenciones

- Python 3.12. Entorno en `.venv/`. Ejecutar con `.venv/bin/python`.
- Código, nombres y docstrings en español. PEP 8, líneas de máximo 88 caracteres (`setup.cfg`).
- Tests en `tests/test_<modulo>.py`. Los tests no escriben fuera de `tmp_path`.
- El código no depende del directorio actual: las rutas se resuelven con `pathlib` desde la raíz del repo.

## Dueños: sprint 1

| Ola | Agente | Modelo | Archivos |
|---|---|---|---|
| 1.0 | Orquestador | Opus | `planificador/io_datos/esquema.py`, `docs/contrato.md` |
| 1.1 | A | Haiku | `requirements.txt`, `pytest.ini`, `setup.cfg`, `.gitignore`, `README.md`, `planificador/**/__init__.py`, `herramientas/__init__.py`, `tests/__init__.py`, `tests/test_humo.py` |
| 1.1 | B | Sonnet | `herramientas/auditoria_horas.py`, `tests/test_auditoria.py` |
| 1.1 | C | Sonnet | `planificador/io_datos/plantilla.py`, `tests/test_plantilla.py` |
