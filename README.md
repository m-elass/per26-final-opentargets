# Servidor de Consulta de Open Targets

**Autor:** Mohamed Elassouti
**Repositorio:** [per26-final-opentargets](https://github.com/m-elass/per26-final-opentargets.git)
**Asignatura:** Programación en Entornos de Red (PER)

Servidor HTTP en Python (sin frameworks) que consulta dianas terapéuticas
y enfermedades de la plataforma [Open Targets](https://platform.opentargets.org/),
basado en el modelo de clases de la práctica anterior.

---

## 1. Cómo arrancar el servidor

```bash
# 1. Instalar la única dependencia externa
pip install requests

# 2. Arrancar el servidor
python servidor.py
```

Se queda escuchando en `http://127.0.0.1:21080` hasta que pulses `Ctrl+C`.

### Lanzar los tests

```bash
python -m unittest unittests.py -v
```

Hay **42 pruebas** que cubren todas las áreas 
(filtrado, ordenación, parseo, casos vacíos, polimorfismo de evidencias…).

---

## 2. Estructura del proyecto

```
.
├── servidor.py            # Servidor HTTP (clase ServidorOpenTargets)
├── target.py              # Clases Target y TractabilityItem
├── disease.py             # Clase Disease (con prefijos ampliados)
├── evidence.py            # Jerarquía Evidence / GeneticEvidence / IndirectEvidence
├── association.py         # Clase Association
├── procesar_api.py        # JSON crudo -> objetos del modelo
├── data1.py               # Consultas GraphQL a la API real
├── data_local.py          # Lectura de ficheros JSON locales
├── data_local.json        # Datos locales (target -> enfermedades)
├── disease_local.json     # Datos locales (enfermedad -> targets)
├── index.html             # Pantalla de búsqueda
├── autor.html             # Pantalla del autor
├── unittests.py           # Batería de 40 pruebas
├── .gitlab-ci.yml         # Configuración de CI
├── .gitignore             # Ficheros ignorados por git
└── README.md              # Este documento
```

---

## 3. Origen de los datos: dualidad API / Local

He implementado **ambas opciones** y el usuario puede elegir desde el
selector "Origen de datos" del formulario.

### 3.1 Modo API (por defecto)

Consulta en tiempo real la **API GraphQL de Open Targets** en el endpoint
`https://api.platform.opentargets.org/api/v4/graphql`. Uso dos queries
distintas según la ruta:

- `data1.py::obtener_datos_api(gene_id)`: parte de un Target y trae sus
  enfermedades asociadas (con sus evidencias). La uso en `/resultados` y
  en `/searchTarget`.
- `data1.py::obtener_targets_de_disease(efo_id)`: query **inversa**, parte
  de una Disease y devuelve los Targets asociados con su score agregado.
  La uso en `/searchDisease`.

**Tamaño de las queries.** Inicialmente intenté pedir 100 enfermedades con
800 evidencias cada una, pero la API me devolvía:

```json
{"errors": [{"message": "Query is too expensive..."}]}
```

He bajado los límites a `size: 25` enfermedades y `size: 50` evidencias.
Para una práctica es de sobra, y la API responde rápido.

**Caché en memoria.** `data1.py` tiene un diccionario que cachea las
respuestas. La primera consulta tarda 1-2s, las siguientes son
instantáneas. Esto hace que el botón "Volver al buscador" y los
filtrados sucesivos no tengan latencia.

### 3.2 Modo Local

Se usa cuando el usuario selecciona "📁 Datos locales (JSON)" en el
formulario. Lee de dos ficheros con la misma estructura que devuelve
la API:

- `data_local.json`: estructura `target -> diseases -> evidences`. Lo
  uso para `/resultados` y `/searchTarget`.
- `disease_local.json`: estructura `disease -> targets`. Lo uso para
  `/searchDisease`. Su contenido está basado en los datos que el
  Rubén compartió en el repositorio de la asignatura.

Como ambos ficheros respetan la estructura de la API, **reutilizo el
mismo procesador** (`procesar_api.py`) sin tocar nada. Solo cambia la
función que carga el JSON crudo (`obtener_datos_local` vs
`obtener_datos_api`).

---

## 4. Decisiones de diseño justificadas

### 4.1 Prefijos válidos en `Disease`

El enunciado de la práctica anterior decía que el `id` de una `Disease`
**debe empezar por `EFO_`**. Sin embargo, al cargar datos reales de Open
Targets resulta que muchas enfermedades vienen con otros prefijos
(`MONDO_`, `Orphanet_`, `HP_`, `DOID_`, etc.) porque la plataforma integra
varias ontologías.

He ampliado la lista de prefijos aceptados a 9 ontologías reconocidas
por Open Targets. Esto no rompe el contrato de la clase (sigue
rechazando cosas como `INVENTADO_1`) y permite que la práctica funcione
con datos del mundo real sin descartar el ~70% de las enfermedades.

### 4.2 Lista de fenotipos vacía al cargar desde la API

`procesar_api.py` crea las `Disease` con una lista de fenotipos vacía:

```python
mi_disease = Disease(datos_enfermedad["id"], datos_enfermedad["name"], [])
```

**Justificación**: la práctica del servidor no usa fenotipos ni en el
formulario ni en la tabla de resultados. Pedirlos a la API engorda
mucho la query (`size` máximo más bajo, latencia más alta). Como la
clase `Disease` sigue siendo capaz de gestionar fenotipos
(`has_phenotype`), pruebo esa funcionalidad en `unittests.py` con
datos sintéticos en lugar de obligar a cargarlos.

### 4.3 Mapeo de evidencias 

La API de Open Targets devuelve evidencias con muchos `datatypeId`
distintos (`genetic_association`, `literature`, `affected_pathway`,
`known_drug`, `animal_model`, `somatic_mutation`, etc.). El modelo de
la práctica solo tiene 3 clases (`Evidence`, `GeneticEvidence`,
`IndirectEvidence`).

**Mi decisión**:

- `genetic_association` → `GeneticEvidence` (que tiene `sourceId` adicional)
- el resto → `Evidence` base
- `IndirectEvidence` **no se instancia desde la API** porque no tengo una
  forma fiable de saber si una evidencia ha sido propagada por ontología
  EFO descendiente. Sería marcarlas "a ojo".

La clase `IndirectEvidence` no queda inútil: se prueba en
`unittests.py` con datos sintéticos para verificar el polimorfismo
del `get_score() * 0.8` (ver `test_12` y `test_15`).

### 4.4 Target por defecto cuando no se proporciona

El README dice que el formulario puede enviarse con cualquier campo
vacío. Pero la API GraphQL **necesita un target como punto de entrada**
para empezar a consultar. Cuando el usuario hace una búsqueda sin
`targetID` y con `source=api`, uso `ENSG00000141510` (TP53) por defecto
**y muestro un aviso visible** en la página de resultados. 

En modo `source=local`, este problema no existe: si no hay targetID,
devuelvo el contenido entero del fichero local.

---

## 5. Rutas del servidor

| Ruta | Método(s) | Qué hace |
|---|---|---|
| `/`, `/index.html`, `/index.htm` | GET | Página de búsqueda (`index.html`) |
| `/autor` | GET | Información del autor (`autor.html`) |
| `/resultados` | GET / POST | Búsqueda general. Tabla completa. |
| `/searchTarget` | GET / POST | Vista enfocada en un Target → sus enfermedades |
| `/searchDisease` | GET / POST | **Query inversa**: una Disease → sus Targets |
| `/resultados/download` | GET | Descarga de los resultados actuales en JSON |
| `/searchTarget/download` | GET | Descarga (idem) |
| `/searchDisease/download` | GET | Descarga (idem) |
| cualquier otra | — | **404** con el texto exacto `"Página no encontrada."` |

---

## 6. Validación de parámetros y manejo de errores

| Situación | Respuesta |
|---|---|
| Score no numérico (`mscore=abc`) | HTTP 400 + `"La consulta no tiene los datos bien formados."` |
| Score fuera de rango (`mscore=2.5`) | HTTP 400 + mensaje explicativo |
| `source` con un valor raro | Se ignora y se usa `api` por defecto |
| Búsqueda sin resultados | HTTP 200 + `"No se han encontrado asociaciones..."` |
| Ruta inexistente | HTTP 404 + `"Página no encontrada."` |
| Excepción inesperada en runtime | HTTP 500 + mensaje (el servidor no se cae) |

---

## 7. Arquitectura modular

`servidor.py` está pensado para ser fácil de probar. La lógica de
búsqueda se reparte en **5 funciones pequeñas con una responsabilidad
clara cada una**, en lugar de un único método:

```
do_GET / do_POST                  -> routing 
   └── procesar_busqueda          -> orquesta los 5 pasos:
        ├── parsear_parametros    -> 1. query string -> dict
        ├── validar_parametros    -> 2. validación + normalización
        ├── cargar_asociaciones_* -> 3. API o local según la fuente
        ├── filtrar_asociaciones  -> 4. aplica los 3 filtros + sort
        └── render_tabla          -> 5. HTML final
```

Esto facilita los unittests: cada función es testeable por separado
sin tocar sockets ni HTTP real. Se ve en `unittests.py`, donde uso
`ServidorOpenTargets.__new__(ServidorOpenTargets)` para instanciar el
handler **sin pasar por el constructor de `BaseHTTPRequestHandler`**
(que necesitaría un socket real).

---

## 8. Extras implementados


|  Conexión API real GraphQL |
|  Dualidad API / Local | 
|  Soporte método POST |
|  Descarga de resultados en JSON | 

### Estructura del JSON descargable

Cuando el usuario pulsa "Descargar resultados", el servidor responde
con un fichero `opentargets_resultados.json` con esta forma:

```json
{
  "metadata": {
    "consulta": {
      "targetID": "ENSG00000141510",
      "diseaseID": "",
      "score_minimo": 0.5,
      "origen_datos": "api"
    },
    "total_resultados": 7
  },
  "asociaciones": [
    {
      "target": {
        "id": "ENSG00000141510",
        "approvedSymbol": "TP53",
        "biotype": "protein_coding",
        "is_druggable": true
      },
      "disease": {
        "id": "EFO_0000305",
        "name": "breast carcinoma"
      },
      "score_total": 0.84,
      "n_evidencias": 4,
      "evidencias": [
        {
          "id": "ev_tp53_brca_1",
          "score": 0.92,
          "datatypeId": "genetic_association",
          "tipo": "GeneticEvidence"
        }
      ]
    }
  ]
}
```

- `metadata`: refleja la consulta exacta que generó este JSON
  (útil para reproducibilidad y debugging).
- `asociaciones`: lista ordenada de mayor a menor score, con todos los
  detalles del modelo (target, disease, score total, número y detalle
  de evidencias, tipo de clase Python de cada evidencia).

---

## 9. Pruebas unitarias (42 tests)

Organizadas por área:

| Suite | Tests | Cubre |
|---|---|---|
| `TestTarget` | 4 | Validación de `ENSG`, `is_druggable`, igualdad por ID |
| `TestDisease` | 5 | Prefijos válidos (EFO, MONDO…), nombre vacío, `has_phenotype` case-insensitive |
| `TestEvidence` | 3 | Score fuera de rango, regla `gwas_catalog`, polimorfismo de `IndirectEvidence` (*0.8) |
| `TestAssociation` | 5 | Media de scores, sin evidencias, mezcla directa/indirecta, `__lt__` |
| `TestFiltrado` | 6 | Filtrado por target, disease, score, combinaciones, caso vacío |
| `TestParsearParametros` | 4 | Query completa, vacía, con `%20`, parcial |
| `TestValidarParametros` | 5 | Score válido / no numérico / fuera de rango, todo vacío, `source` inválido |
| `TestColumnasPorRuta` | 5 | Cada ruta muestra las columnas adecuadas, incluyendo tipo de evidencia |
| `TestProcesadoLocal` | 5 | Integración con `data_local.json` y `disease_local.json`, errores API, JSON inválido |

Cubro los **4 aspectos mínimos** pedidos en el README:

1.  Filtrado lógico (target, disease, score) — suite `TestFiltrado`
2.  Ordenación con `__lt__` — `test_17`
3.  Query strings (vacías, mal formadas) — `TestParsearParametros` + `TestValidarParametros`
4. Casos vacíos — `test_23`, `test_38`, `test_39`, `test_40`

---

## 10. Cómo usar la interfaz

Al abrir `http://127.0.0.1:21080/` hay una página con **4 pestañas**:

1. **Búsqueda general**: Target ID + Disease ID + Score, los tres
   opcionales. Lleva a `/resultados`.
2. **Por Target**: solo Target ID. Lleva a `/searchTarget`, que muestra
   las enfermedades asociadas a ese gen.
3. **Por Disease**: solo Disease ID. Lleva a `/searchDisease`, que
   muestra los Targets asociados a esa enfermedad (query inversa).
4. **POST**: idéntica a la búsqueda general pero envía los datos por
   POST (cuerpo en lugar de URL). Es el extra de soporte multimetodo.

Cada formulario tiene un selector de **Origen de datos** que permite
elegir entre API o local en cualquier momento.

### Detalle visual: efectos de envío

Como toque personal he añadido un selector de efectos visuales al
darle a "Buscar":

- **⚡ Hollow Purple** (defecto): animación de fusión azul + rojo →
  morado.
- **🌌 Void Rift**: pantalla fragmentada absorbida por un agujero negro.
- **⏸ Sin efecto**: envío instantáneo (útil al depurar).

La elección se guarda en una **cookie** del navegador, así persiste
entre recargas sin necesidad de localStorage .

---
