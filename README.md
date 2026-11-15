# Agente planificador de horarios

Agente que genera horarios sin cruces para un programa académico. Parte de la
asignación de bloques de clase a franjas, días y salones, y busca una solución
factible de costo mínimo (o lo más cercana posible) con distintos algoritmos de
búsqueda.

Proyecto del curso *Representación y solución automática de problemas*,
Universidad del Rosario.

Autores: Manuel Cruz y Santiago Peña.

## Formalización

- **Estado.** Una asignación parcial X: cada bloque m ocupa una posición
  (día, franja de inicio, salón). U(X) es el conjunto de bloques sin ubicar.
- **Ocupación.** Un bloque de duración δ ocupa δ franjas consecutivas del mismo
  día y del mismo salón.
- **Acciones.** Añadir(m, p), Eliminar(m), Intercambiar(m, m'), Reubicar(m, p)
  y CambiarSalón(m, s).
- **Restricciones duras de legalidad.** El bloque debe caber en la jornada. Un
  bloque virtual solo va en un salón virtual, y un bloque presencial no va en
  uno. En un salón presencial deben cumplirse tipo y capacidad (≥ estudiantes
  del bloque) y las celdas deben estar libres. Los salones virtuales no tienen
  límite de capacidad ni de ocupación simultánea.
- **Restricciones de solución (v(X) = 0).** Disponibilidad del docente, ventana
  de matrícula del grupo y ningún traslape entre bloques vecinos en el grafo de
  conflictos Γ (comparten docente o algún grupo). El generador de acciones no
  filtra estas tres; se cuentan como violaciones en v(X). Los solvers sí las
  usan para podar el dominio de cada bloque.
- **Objetivo blando.** f(X) = Σ wᵢ·φᵢ(X): huecos de docentes y grupos,
  dispersión de docentes, carga diaria, horas extremas y cambios de sede.
- **Costo total.** F(X) = f(X) + λ·v(X), con λ = `pesos.lam` o, por defecto, una
  cota superior de f + 1, para que una violación pese más que cualquier mejora
  posible en f.

## Algoritmos

| Algoritmo | Clave | Descripción |
|---|---|---|
| Backtracking (CSP) | `backtracking` | Backtracking (CSP) con MRV + grado y forward checking. Modos `primera` y `optimizar`. |
| A* | `a_estrella` | A* con heurística admisible y consistente (óptimo en costo aditivo). |
| Avara | `avara` | Búsqueda avara: heurística de distancia a la meta (no admisible). |
| Beam search | `beam` | Beam search: conserva los k mejores nodos por nivel (g + h). |
| Reparación | `reparar()` en `planificador/algoritmos/reparacion.py` | Repara un horario vigente tras un cambio de disponibilidad, buscando una solución factible cercana a la original. |

Las claves de la tabla son las de `planificador/algoritmos/registro.py`
(`REGISTRO`), que usan la interfaz y los experimentos.

## Estructura

```
.
├── README.md
├── requirements.txt        dependencias con versión fijada
├── pytest.ini              configuración de pytest
├── setup.cfg               configuración de flake8 (líneas de 88 caracteres)
├── .gitignore              excluye .venv/, salidas/ y los datos reales
├── docs/
│   └── contrato.md         reglas de desarrollo y firmas congeladas de la API
├── planificador/
│   ├── core/               modelo (entidades y acciones), estado, acciones,
│   │                       conflictos (Γ), costo (v, f, F) y validador independiente
│   ├── algoritmos/         base (interfaz Solver), comun, backtracking,
│   │                       informada (A* y avara), beam, reparacion,
│   │                       registro y reproduccion (cuadros de animación)
│   ├── io_datos/           esquema (formato de entrada), plantilla (genera el
│   │                       Excel de entrada) y sintetico (instancias de prueba)
│   ├── experimentos/       runner (ejecuta configuraciones), graficas (PNG y
│   │                       tabla resumen) y configs/ (rapido, base, beam_ancho)
│   └── app/                interfaz Streamlit: main (navegación), páginas
│                           pagina_instancia, pagina_ejecutar y pagina_comparar,
│                           y módulos sin Streamlit (vistas, edicion, ejecucion, graficas)
├── herramientas/
│   └── auditoria_horas.py  auditoría de horas: calendario académico vs. malla (solo lectura)
├── tests/                  pruebas con pytest (fixtures en tests/fixtures/)
└── salidas/                resultados generados (no se versiona)
```

## Instalación

Requiere Python 3.12.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Uso

Todos los comandos se ejecutan desde la raíz del repositorio. Los módulos de
`planificador/` se invocan con `-m`, para que encuentren el paquete.

### Interfaz

```bash
.venv/bin/streamlit run planificador/app/main.py
```

- **Instancia**: genera una instancia sintética, la carga, la edita y la guarda.
- **Ejecutar y animar**: corre un algoritmo sobre la instancia y reproduce su
  búsqueda paso a paso.
- **Comparar**: ejecuta varios algoritmos sobre la misma instancia y compara
  sus resultados.

### Experimentos

```bash
.venv/bin/python -m planificador.experimentos.runner --config planificador/experimentos/configs/rapido.json
.venv/bin/python -m planificador.experimentos.runner --config planificador/experimentos/configs/base.json
.venv/bin/python -m planificador.experimentos.runner --config planificador/experimentos/configs/beam_ancho.json
.venv/bin/python -m planificador.experimentos.graficas --csv salidas/experimentos/rapido/resultados.csv
```

- `rapido.json`: corrida corta de comprobación (una semilla, un tamaño).
- `base.json`: malla completa de comparación (varias semillas, tamaños,
  dificultades, escenarios y algoritmos). Es una corrida larga.
- `beam_ancho.json`: barrido del ancho k del beam search.
- `graficas`: genera los PNG y `tabla_resumen.md` en la carpeta del CSV indicado
  (o en la de `--salida`). Para otra configuración, cambie la ruta de `--csv`
  por la de su `resultados.csv`.

El runner escribe en `salidas/experimentos/<nombre>/` (`resultados.csv` y
`metadata.json`). Ejecutarlo de nuevo sobrescribe esa carpeta; use `--salida`
para escribir en otra.

### Generar una instancia sintética

```bash
.venv/bin/python -m planificador.io_datos.sintetico --bloques 50 --semilla 0
```

Opciones: `--bloques` (número de bloques), `--semilla` y `--salida` (ruta del
JSON). Por defecto guarda en `salidas/instancias/`. La instancia incluye una
solución oculta que sirve de referencia.

### Plantilla de entrada

```bash
.venv/bin/python -m planificador.io_datos.plantilla
.venv/bin/python -m planificador.io_datos.plantilla --sin-ejemplos
```

Genera el libro Excel de entrada a partir de `planificador/io_datos/esquema.py`.
Por defecto guarda en `salidas/plantilla_entrada_BORRADOR.xlsx`. Con
`--sin-ejemplos` no incluye filas de ejemplo. Opción adicional: `--salida`.

### Auditoría de horas

```bash
.venv/bin/python herramientas/auditoria_horas.py
```

Compara las horas programadas en el calendario académico con las que exige la
malla curricular, y genera `salidas/auditoria_horas.xlsx`. Es una herramienta de
solo lectura.

Requiere los Excel originales de la malla curricular y del calendario académico.
Esos archivos contienen datos personales y no se versionan. Use `--malla` y
`--calendario` para indicar sus rutas, y `--hojas` para elegir las hojas del
calendario que se auditan.

### Pruebas y estilo

```bash
.venv/bin/pytest
.venv/bin/flake8
```

Algunas pruebas están marcadas como `integracion` y se omiten si no existen los
Excel reales.

## Reproducibilidad

- Las configuraciones de `planificador/experimentos/configs/` fijan las semillas
  (`"semillas"`). El generador sintético recibe la semilla con `--semilla`.
- Los solvers son deterministas: con los mismos datos y parámetros dan el mismo
  resultado.
- Cada corrida del runner guarda en `metadata.json` la configuración, las
  versiones de Python y de las librerías, y la fecha. Con esto se puede repetir
  el experimento.
- Las columnas de tiempo (`tiempo_s`) dependen del reloj de la máquina y no son
  reproducibles. El resto de columnas sí lo son.
- `salidas/` está excluido de git (`.gitignore`), igual que los datos reales.

## Capturas

### Instancia

Pendiente: captura de la página Instancia.

### Ejecutar y animar

Pendiente: captura de la página Ejecutar y animar.

### Comparar

Pendiente: captura de la página Comparar.

## Estado del proyecto

- **Sprints 1 a 4 completos**: esqueleto del proyecto y esquema de entrada;
  núcleo genérico (modelo, estado, acciones, costo y validador); algoritmos de
  búsqueda y reparación; experimentos e interfaz.
- **Pendiente, sprint 5**:
  - importador de la plantilla de entrada;
  - importadores de los Excel reales;
  - exportador del cronograma oficial;
  - Q-learning (opcional);
  - notebook de demostración.

## Uso de IA

Partes del código se desarrollaron con asistencia de IA y fueron revisadas por
los autores, que deben poder explicarlas en la sustentación.
