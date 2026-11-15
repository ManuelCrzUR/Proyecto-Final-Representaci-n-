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

## Sprint 2: API del core (contrato)

Las entidades, la `Posicion`, las acciones (`Anadir`, `Eliminar`, `Intercambiar`, `Reubicar`, `CambiarSalon`) y `celdas_de` están en `planificador/core/modelo.py`, que está congelado. Los módulos siguientes deben exponer **exactamente** estas firmas.

### `core/estado.py` (agente D)
- `class Estado(instancia, asignacion: dict[str, Posicion] | None = None)`
  - `.instancia`; `.asignacion` → vista de solo lectura bloque_id → Posicion
  - `.sin_ubicar() -> frozenset[str]`: U(X)
  - `.posicion(bloque_id) -> Posicion | None`
  - `.bloques_en(celda) -> frozenset[str]`: bloques que ocupan la celda (dia, franja) en cualquier salón
  - `.ocupante(salon_id, celda) -> str | None`: bloque en ese salón y celda (siempre None si el salón es virtual)
  - `.copiar() -> Estado`; `.clave() -> Hashable` (igual para asignaciones iguales); `__eq__` y `__hash__` coherentes con `clave()`
  - Mutadores de bajo nivel: `._colocar(bloque_id, pos)` y `._quitar(bloque_id)`. Los usa `acciones.py`, y como excepción documentada también `algoritmos/reparacion.py`, para armar el estado vigente omitiendo los bloques que chocan.
  - API extra estable (agregada en la ola 2.1): `.ocupacion_docente(docente_id, celda) -> int` y `.ocupacion_grupo(grupo_id, celda) -> int`.
  - `Estado` es mutable: no se debe mutar mientras sea clave de un dict o miembro de un set. `acciones_legales` es un generador sobre el estado vivo, así que hay que materializarlo con `list()` antes de mutar.

### `core/acciones.py` (agente D)
- `es_legal(estado, accion) -> bool`
- `aplicar(estado, accion) -> Estado`: pura, devuelve un estado nuevo. Lanza `ValueError` si la acción es ilegal.
- `aplicar_en_sitio(estado, accion) -> Accion`: muta el estado y devuelve la acción inversa (para deshacer en la búsqueda).
- `posiciones_legales(estado, bloque_id) -> list[Posicion]`: posiciones donde **añadir** el bloque, en orden determinista (dia, franja, salon). El bloque se ignora a sí mismo si ya está ubicado.
- `acciones_legales(estado) -> Iterator[Accion]`: todas las acciones legales, en orden determinista.
- **Legalidad** (según la propuesta): solo restricciones de salón y de forma. **No** filtra A, W ni Γ: esos incumplimientos se cuentan en v(X).
  - `0 <= dia < D` y `franja + duracion <= H`.
  - Si `bloque.virtual`, el salón debe ser virtual. Si no, el salón no puede ser virtual.
  - Si el salón no es virtual: `tipo_salon is None or tipo_salon == salon.tipo`, `capacidad is None or capacidad >= E(m)`, y las celdas libres en ese salón.
  - `Anadir`: el bloque está en U. `Eliminar`, `Reubicar` y `CambiarSalon`: el bloque está ubicado. `Intercambiar`: ambos están ubicados, tienen igual duración y cada uno es legal en la posición del otro.

### `core/conflictos.py` (agente E)
- `construir_conflictos(instancia) -> dict[str, frozenset[str]]`: Γ. Dos bloques son vecinos si comparten `docente_id` (no None) o al menos un grupo. Un bloque no es vecino de sí mismo.
- `grado(conflictos, bloque_id) -> int`

### `core/costo.py` (agente E)
- `Violaciones(sin_ubicar, disponibilidad, ventana, conflicto, salon)` con `.total` está **definida en `modelo.py`**. `costo.py` y `validador.py` la importan de ahí. `salon` cuenta celdas con dos bloques en un salón no virtual o con capacidad o tipo inválidos; con acciones legales siempre vale 0.
- `violaciones(estado) -> Violaciones`; `v(estado) -> int`
  - `disponibilidad`: franjas ubicadas con docente y (d, h) ∉ disponibilidad.
  - `ventana`: suma, por grupo del bloque, de las franjas con (d, h) ∉ ventana del grupo.
  - `conflicto`: número de pares {m, m'} vecinos en Γ × franjas en que se traslapan.
- `desglose_f(estado) -> dict[str, float]` (φ_i sin pesos); `f(estado) -> float` = Σ w_i φ_i
  - `hueco_docente` / `hueco_grupo`: por entidad y día, franjas vacías entre la primera y la última ocupada.
  - `dispersion_docente`: por docente, días con clase − ⌈franjas totales / H⌉, con mínimo 0.
  - `carga_grupo`: por grupo o docente y día, exceso sobre `max_franjas_dia` (si está definido).
  - `hora_extrema`: franjas ubicadas con `franja.extrema`.
  - `cambio_sede`: por grupo y día, pares de bloques consecutivos en el tiempo con sedes distintas (se ignoran los virtuales).
- `cota_superior_f(instancia) -> float`; `lam(instancia) -> float` = `pesos.lam` o `cota_superior_f + 1`
- `F(estado) -> float` = f + λ·v; `recompensa(antes, despues) -> float` = F(antes) − F(despues)

### `core/validador.py` (agente E)
- `validar(instancia, asignacion: dict[str, Posicion]) -> Reporte`, donde `Reporte(violaciones: Violaciones, f: float, F: float, problemas: list[str])`. Los problemas van en texto legible en español.
- **Independiente:** no importa `estado.py`, `acciones.py` ni `costo.py`, solo `modelo.py`. Recalcula todo desde cero. Sirve de oráculo para los tests.

## Dueños: sprint 2

| Ola | Agente | Modelo | Archivos |
|---|---|---|---|
| 2.0 | Orquestador | Opus | `planificador/core/modelo.py`, `docs/contrato.md` |
| 2.1 | D | Sonnet | `planificador/core/estado.py`, `planificador/core/acciones.py`, `tests/test_estado_acciones.py` |
| 2.1 | E | Sonnet | `planificador/core/conflictos.py`, `planificador/core/costo.py`, `planificador/core/validador.py`, `tests/test_costo.py`, `tests/test_validador.py` |
| 2.1 | F | Haiku | `tests/fixtures/__init__.py`, `tests/fixtures/instancias_mini.py`, `tests/test_fixtures.py` |
| 2.2 | G | Sonnet | `planificador/io_datos/sintetico.py`, `tests/test_sintetico.py` |

## Sprint 3: algoritmos (contrato)

`planificador/algoritmos/base.py` (congelado) define `Solver`, `Limites`, `Evento`, `Traza`, `Resultado`, `Presupuesto` y `foto`. `planificador/algoritmos/comun.py` es del orquestador y define `dominio_unario`, `consistente`, `dominio_consistente`, `elegir_mrv` y `resultado_desde`.

**Reglas comunes a todos los solvers:**
- Son una subclase de `Solver`, con atributo de clase `nombre` y los parámetros en `__init__(**parametros)`.
- `resolver(instancia, estado_inicial=None, limites=Limites())` no muta `estado_inicial`. Los bloques ya ubicados en él quedan **fijos**: solo se ubican los bloques de U(X).
- Respetan el `Presupuesto`: incrementan `nodos_expandidos` y `nodos_generados`, y revisan `agotado()` en cada expansión.
- **Siempre** devuelven el mejor estado encontrado, con el menor F, mediante `resultado_desde`. `terminado_por` ∈ {meta, agotado, limite_nodos, limite_tiempo}.
- Registran la traza con los tipos de `TIPOS_EVENTO`. Los eventos `add` y `del` llevan bloque y posición. En A\*, avara y beam, el evento `expandir` lleva `asignacion=foto(...)`. Al final se registra un evento `fin` con `nota=terminado_por`.
- Son deterministas: con los mismos datos dan el mismo resultado. Si usan azar, la semilla es un parámetro.
- **Saltar un bloque:** si un bloque no tiene dominio consistente, la búsqueda puede dejarlo sin ubicar, y eso cuesta 1 en v por U(X). Así el solver devuelve siempre un horario lo más completo posible, aun en instancias infactibles.

**Costo de camino de A\*, avara y beam (aditivo y monótono):**
- Un nodo es un estado parcial más el conjunto de bloques ya **decididos** (ubicados o saltados). La variable a decidir se elige con `elegir_mrv` sobre los no decididos, y los sucesores son sus posiciones de `dominio_unario`, más la opción "saltar".
- g(n) = λ·[v_disp + v_vent + v_conf + #saltados](n) + w_ext·φ_extrema(n) + w_carga·φ_carga(n). Todos esos términos solo crecen al decidir bloques, así que el costo de paso es ≥ 0.
- Los huecos, la dispersión y el cambio de sede **no son aditivos**: un bloque puede rellenar un hueco y bajar el costo. Por eso no entran en g. Se evalúan al final con F completo y se reportan. Esto se discute en el informe.
- h(n) = λ·#(no decididos con dominio consistente vacío) + Σ_no decididos w_ext·min_{p ∈ dominio consistente} franjas extremas de p. Es admisible porque cada término es una cota inferior independiente del costo futuro de su bloque.
- Avara: f(n) = h(n). A\*: f(n) = g(n) + h(n). Beam: conserva los k mejores por g + h en cada nivel.

## Dueños: sprint 3

| Ola | Agente | Modelo | Archivos |
|---|---|---|---|
| 3.0 | Orquestador | Opus | `algoritmos/base.py`, `algoritmos/comun.py`, `tests/test_algoritmos_base.py`, `docs/contrato.md` |
| 3.1 | H | Sonnet | `algoritmos/backtracking.py`, `tests/test_backtracking.py` |
| 3.1 | I | Sonnet | `algoritmos/informada.py` (nodo, g, h y sucesores compartidos; avara y A\*), `algoritmos/beam.py`, `tests/test_informada.py`, `tests/test_beam.py` |
| 3.2 | K | Sonnet | `algoritmos/reparacion.py`, `tests/test_reparacion.py` |
| 3.2 | L | Haiku | `tests/test_solvers_cruzado.py` |
