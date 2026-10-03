# Asistente BBVA — Sistema RAG con Web Scraping

Asistente conversacional que responde preguntas sobre el contenido del sitio
público de BBVA Colombia (<https://www.bbva.com.co/>) usando RAG. Prueba técnica de Machine Learning Engineer.

> **Estado: trabajo en progreso.** Este README se actualiza junto con el código.

## Estado del proyecto

| Etapa | Estado |
|---|---|
| 1. Scraping: descarga del HTML crudo | Hecho |
| 2. Limpieza y normalización del HTML | Hecho |
| 3. Chunking | Hecho |
| 4. Vectorización e indexación | Hecho |
| 5. Recuperación y generación (LLM) | Siguiente |
| 6. Interfaz conversacional | Pendiente |
| 7. Historial de conversación por ID | Pendiente |
| 8. Análisis del historial (métricas) | Pendiente |
| 9. Dockerización | Pendiente |

## Flujo de datos

```
sitemap.xml ---> [1. SCRAPER] ---> data/raw/*.html + manifest.jsonl
                                          |
                                          v
                                   [2. LIMPIEZA] ---> data/clean/paginas.jsonl
                                                      data/clean/descartadas.jsonl
                                          |
                                          v
                                   [3. CHUNKING] ---> data/clean/chunks.jsonl
                                          |
                                          v
                          [4. EMBEDDINGS + BASE VECTORIAL] ---> data/chroma/
                                          |
                                          v
                          [5. RAG: recuperación + LLM local]   (siguiente)
```

Las etapas están separadas a propósito: el scraper solo descarga y guarda HTML
sin transformarlo. Toda la limpieza ocurre después, a partir de los datos crudos. 
Así se puede corregir o cambiar la limpieza sin volver a scrapear el sitio.

## Estructura del repositorio - pensada inicialmente

```
Asistente_BBVA/
├── data/
│   ├── raw/                   # HTML crudo + manifest.jsonl 
│   ├── clean/                 # paginas, descartadas y chunks (.jsonl, sí se versiona)
│   └── chroma/                # base vectorial local 
├── src/
│   ├── config.py              # configuración desde .env              (done)
│   ├── scraping/
│   │   └── scraper.py         # descarga paralela del HTML crudo      (done)
│   ├── ingestion/
│   │   └── limpieza.py        # HTML crudo -> texto limpio            (done)
│   │   ├── chunking.py        # páginas -> chunks (Strategy)          (done)
│   │   └── indexador.py       # chunks -> embeddings -> Chroma        (done)
│   ├── providers/
│   │   ├── base.py            # interfaces Embeddings / VectorStore   (done)
│   │   ├── local.py           # e5 + Chroma                           (done)
│   │   └── factory.py         # Factory de proveedores                (done)
│   │                          # LLM (Ollama)                          (pendiente)
│   ├── rag/                   # recuperación y generación             (pendiente)
│   ├── memory/                # historial de conversaciones           (pendiente)
│   ├── analytics/             # métricas sobre el historial           (pendiente)
│   └── ui/                    # interfaz conversacional               (pendiente)
└── scripts/                   # - validar si son necesario            (pendiente)
```

## Requisitos previos

Para las etapas implementadas (scraping, limpieza, chunking e indexación):

- Python 3.13.5.
- **Google Chrome instalado**, pero solo si se va a ejecutar el scraper (paso 3,
  opcional). Se lanza con `channel="chrome"`.
- Conexión a internet para el scraper.

- Unos 2 GB libres en disco: el entorno virtual con PyTorch ocupa ~1,5 GB y la
  primera ejecución descarga el modelo de embeddings (~470 MB).

Todavía no hay Docker. Las variables de entorno son opcionales: todo tiene un valor
por defecto y `.env.example` lista los parámetros (cópialo a `.env` para cambiarlos).

## Instrucciones paso a paso

### 1. Clonar y crear el entorno

```bash
git clone https://github.com/andresgarces834/Asistente_BBVA
cd Asistente_BBVA
python -m venv .venv
```

Activar el entorno:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

### 2. Instalar dependencias

```bash
python -m pip install -r requirements.txt
```

### 3. Ejecutar el scraper

**Este paso y el siguiente son opcionales para reproducir el proyecto.** El HTML
crudo (`data/raw/`) no está en el repositorio porque pesa ~465 MB, pero sí los datos
limpios y los chunks (`data/clean/`, unos 14 MB), que es lo que usan las etapas
siguientes. Solo hace falta scrapear para refrescar los datos.

# Sitio completo

```bash
python -m src.scraping.scraper
```

Opciones:

| Argumento | Descripción | Por defecto |
|---|---|---|
| `--limit N` | Máximo de páginas a descargar | todas |
| `--workers N` | Pestañas descargando en paralelo | 10 |
| `--headless` | Chrome sin ventana | desactivado |

Se ejecuta desde la raíz del repositorio y fuera de Docker.

### 4. Ejecutar la limpieza

```bash
python -m src.ingestion.limpieza
```

Lee `data/raw/manifest.jsonl` y genera `data/clean/paginas.jsonl` y
`data/clean/descartadas.jsonl`. No tiene argumentos y tarda alrededor de un
minuto. Es determinista: se puede repetir y sobrescribe la salida sin tocar los
crudos.

El formato es `jsonl` para que cada linea sea una pagina con el objetivo de tener
centralizada toda la información y evitar muchos documentos

### 5. Generar los chunks

```bash
python -m src.ingestion.chunking
```

Lee `data/clean/paginas.jsonl` y genera `data/clean/chunks.jsonl`.

| Argumento | Descripción | Por defecto |
|---|---|---|
| `--estrategia` | `headings` o `fija` | `headings` |
| `--size N` | Caracteres máximos por chunk | 1000 |
| `--overlap N` | Solape al partir una sección larga | 100 |
| `--min-chars N` | Una sección más corta se une a la siguiente | 300 |
| `--salida RUTA` | Archivo de salida | `data/clean/chunks.jsonl` |

### 6. Indexar en la base vectorial

```bash
python -m src.ingestion.indexador
```

Calcula los embeddings de `data/clean/chunks.jsonl` y los guarda en Chroma
(`data/chroma/`). La primera vez descarga el modelo. Con los 7.659 chunks tarda
unos 5 minutos en CPU. Es reanudable: omite los chunks ya indexados.

| Argumento | Descripción |
|---|---|
| `--limit N` | Indexa solo los N primeros chunks (prueba rápida) |
| `--reiniciar` | Borra lo indexado y empieza de cero |

### 7. Cómo usar la interfaz conversacional

*Pendiente.* 

## Etapa 1 — Scraping (implementada)

`src/scraping/scraper.py`:

1. Abre Chrome (con ventana) y entra a la home. El WAF exige una sesión previa
   antes de aceptar otras peticiones.
2. Descarga `sitemap.xml` con ese mismo contexto y extrae las URLs.
3. Filtra: solo el dominio `www.bbva.com.co`, excluye los patrones que
   `robots.txt` prohíbe (`*.content.html`, `/personas/cards`) y elimina
   duplicados conservando el orden.
4. Omite las URLs cuyo archivo ya existe.
5. Descarga las restantes con N pestañas en paralelo a partir de una cola
   compartida, con 1 s de pausa por worker entre páginas.
6. Guarda cada página y registra la relación URL.

**Salida** en `data/raw/`:

- `<hash>.html` — un archivo por página. El nombre es los primeros 16 caracteres
  del SHA-1 de la URL, así que es estable entre ejecuciones.
- `manifest.jsonl` — una línea JSON por página descargada:

```json
{"url": "https://www.bbva.com.co/personas/atencion-al-inversionista/acciones.html", "archivo": "<hash>.html"}
```

**Decisiones de robustez:** escritura atómica (archivo `.tmp` y luego renombrado,
para no dejar `.html` incompletos), una URL fallida no detiene el resto, y si el
navegador se cierra el worker se detiene en vez de fallar en cada URL restante.
Las URLs fallidas no se registran, así que se reintentan en la siguiente corrida.

## Etapa 2 — Limpieza (implementada)

`src/ingestion/limpieza.py`. Entrada: `data/raw/*.html` + `manifest.jsonl`.
Salida: `data/clean/paginas.jsonl` y `data/clean/descartadas.jsonl`.

### Cómo se diseñó: primero se midió, luego se limpió

Antes de escribir reglas se analizaron los 1.240 HTML crudos con ayuda de IA. Dos mediciones
guiaron el diseño:

- **Estructura:** 1.233 páginas tienen un único `<main>` y 7 no tienen; la
  mediana de texto es ~4.000 caracteres. Sobre el contenido se detectaron
  separadores `U+2028`, espacios de ancho cero `U+200B`, espacios
  duros `NBSP` y guiones suaves.
- **Ruido de interfaz:** se contó cuántas páginas repiten cada línea de texto.
  Las líneas que aparecen solas en más del 15 % de las páginas son botones y
  etiquetas, no contenido (`Más información`, `Anterior`, `Siguiente`, `Cerrar`,
  `1 de 1`...). Un caso llamativo: la fecha del día (`PUBLICIDAD` + fecha) la
  inyecta el sitio en 631 páginas y no es contenido.

### Qué hace, por cada página

1. **Extracción.** Toma título (sin el sufijo ` | BBVA Colombia`), descripción y
   el contenido de `<main>`. Se usa solo `<main>` porque el resto de la página
   es cabecera, pie y navegación.
2. **Quita el ruido** en dos capas: elementos HTML (`script`, `style`, `svg`,
   `iframe`...) y componentes de interfaz por clase (migas de pan, botones de
   compartir, navegación de sliders, avisos de cookies); y después, líneas
   sueltas de la lista de ruido medida arriba.
3. **Conserva la estructura:** los títulos se convierten a markdown (`#`, `##`...)
   para poder hacer chunking por secciones, y las listas a `- `. El título de un
   elemento de lista (tarjetas, ilustraciones...) se deja como texto de su viñeta
   y no como un título de sección.
4. **Reconstruye las pestañas:** la etiqueta de cada pestaña se escribe, en negrita,
   delante del contenido de su panel (ver más abajo).
5. **Normaliza Unicode:** `U+2028`/`U+2029` pasan a saltos de línea; se eliminan
   los caracteres invisibles; `NBSP` pasa a espacio normal, se ordenan los
   espacios y saltos de línea.
6. **Metadatos desde la URL:** `seccion`, `categoria` y `subcategoria`, para
   poder filtrar al recuperar.

### Salida

Cada línea de `paginas.jsonl`:

```json
{
  "url": "https://www.bbva.com.co/personas/productos/cuentas/ahorro/blue.html",
  "seccion": "personas", "categoria": "productos", "subcategoria": "cuentas",
  "titulo": "Cuenta de Ahorro Blue",
  "descripcion": "...",
  "headings": ["Cuenta de Ahorro Blue", "Ventajas", "..."],
  "texto": "# ...\n\n- ...",
  "archivo_raw": "<hash>.html"
}
```

`archivo_raw` permite volver al HTML original de cada registro.

### Resultado

| | Páginas |
|---|---|
| En el manifest | 1.240 |
| Limpias (`paginas.jsonl`) | 1.201 |
| Descartadas (`descartadas.jsonl`) | 39 |

Una página se **descarta** si no tiene `<main>` o si tras limpiar le quedan
menos de 200 caracteres. Revisadas una a una, casi todas son simuladores,
formularios, buscadores y organigramas (imágenes): no tienen texto que indexar.
Cada descarte queda registrado con su motivo.

### Decisiones

- **NFC y no NFKC** al normalizar: NFKC convertiría `º` y `ª` en `o` y `a`
  (`N.º`, `1.ª`), algo incorrecto en español.
- **No se usa `<body>` como alternativa** cuando falta `<main>`: arrastraría
  cabecera, pie y cookies al índice; es preferible descartar la página.
- **`lxml` como parser.** Con `html.parser` el resultado fue idéntico en las 1.240
  páginas; `lxml` tolera mejor el HTML mal formado.
- **Reglas medidas, no supuestas:** la lista de ruido sale de la frecuencia real
  de las líneas, no de una intuición sobre el sitio.

### Corrección posterior: pestañas y títulos dentro de viñetas

Al probar el asistente con una pregunta real (*"¿Qué puedo hacer en mi línea
empresarial?"*, cuyo texto es el título de una página de líneas de atención) la
respuesta salió incompleta. Parte de la causa estaba en la limpieza:

- **Las pestañas perdían su etiqueta.** El HTML enlaza cada pestaña (`role="tab"`)
  con su panel (`role="tabpanel"`, por `aria-controls`), pero el texto plano dejaba
  todas las etiquetas juntas y lejos de su contenido: no se sabía qué viñetas eran de
  "Comercio exterior" o de "Leasing". Hay 3.258 pestañas en 738 páginas; la mayoría
  (preguntas frecuentes) repite su título dentro del panel y no pierde nada. Las que
  sí lo pierden son 306 etiquetas en 78 páginas.
- **Solución:** si la etiqueta no aparece como título propio de su panel (empieza
  con ella o hay un texto que es exactamente esa etiqueta), se escribe en negrita
  (`**Comercio exterior**`) delante del contenido y se elimina la lista de
  etiquetas, que quedaba redundante.
- **La etiqueta es una línea en negrita y no un título (`####`)** a propósito: así
  todo el grupo de pestañas sigue siendo una sola sección bajo su título común, y la
  pregunta general ("¿qué puedo hacer en mi línea?") sigue encontrando el contenido.
  Con un título por pestaña, cada una sería un chunk aparte sin el título común.
- **Primer intento descartado:** comprobar si la etiqueta aparecía *en cualquier
  parte* del panel. "Leasing" figura dentro de la frase "Soporte para el pago del
  Leasing", así que daba la etiqueta por presente y no la reconstruía.
- **Títulos dentro de viñetas.** Un elemento de lista cuyo título era un `<h2>`
  quedaba como `- ## Título` (1.642 líneas en 248 páginas). Ahora es `- Título`
  (quedan 5 casos).

## Etapa 3 — Chunking (implementada)

`src/ingestion/chunking.py`. Entrada: `data/clean/paginas.jsonl`. Salida:
`data/clean/chunks.jsonl`.

### Cómo se diseñó

Igual que la limpieza, primero se midió. Al partir las 1.200 páginas por
encabezados salen 15.121 secciones, con una mediana de solo 182 caracteres:

- El 36 % tiene menos de 100 caracteres (por ejemplo, `### FAQs` aparece solo 995
  veces) y el 4 % supera los 1.500, con casos de hasta 20.000.
- Partir únicamente por encabezados no sirve, y partir por tamaño fijo ignora la
  estructura. Por eso se implementaron **ambas estrategias** para compararlas.
- El 21 % del texto de esas secciones es un duplicado exacto de otra (bloques de
  FAQs de tarjetas repetidos en cientos de páginas).

### Estrategias

- **`headings` (por defecto, híbrida):** una sección de tamaño normal es un chunk;
  las secciones muy cortas (menos de 300 caracteres) se unen a la siguiente; una
  que no cabe en 1.000 caracteres se parte con solape, intentando cortar en un
  salto de párrafo o de línea y no a mitad de palabra. **Cada trozo de una sección
  partida repite el título de la sección**, y el corte prefiere caer justo antes
  de una etiqueta de grupo (ver [Corrección posterior](#corrección-posterior-trozos-de-continuación-sin-encabezado)).
- **`fija` (línea base):** ventana de 1.000 caracteres sobre todo el texto, sin
  mirar los encabezados.

### Resultado (1.201 páginas)

| | `headings` | `fija` |
|---|---|---|
| Chunks finales (tras deduplicar) | **7.493** | 5.909 |
| Tamaño mediano | 595 caracteres | 932 |
| Chunks que empiezan con un encabezado | 99 % | 34 % |

Se eligió `headings` porque sus chunks corresponden a secciones reales de la
página (con su título), lo que da fragmentos más coherentes al recuperar. En la
práctica genera 9.547 chunks: descarta 332 de menos de 80 caracteres y 1.722
repetidos.

### Deduplicación

Cada chunk se identifica por una huella del texto (ignorando mayúsculas y
espacios). Si el mismo texto aparece en otra página, se conserva solo la primera
copia y se suma `repeticiones`. El caso más repetido, un bloque de FAQs de
tarjetas, aparecía 238 veces.

### Corrección posterior: trozos de continuación sin encabezado

La misma prueba con *"¿Qué puedo hacer en mi línea empresarial?"* destapó un
defecto del chunking. La página tiene una lista de 24 viñetas bajo ese título; como
la sección mide 1.788 caracteres y un chunk admite 1.000, se partió en dos, y el
segundo (las últimas 10 viñetas) quedó **sin el título**. Sin él, su embedding se parecía poco a la pregunta
(similitud 0,843 frente a un corte de 0,862 para entrar en el top 5), no se
recuperó, y el asistente contestó solo con las primeras 14 viñetas.

No era un caso aislado: 1.100 secciones se parten y **2.315 de los 10.149 chunks
(23 %)** eran trozos de continuación sin título.

**Qué se cambió**

- **Cada trozo de una sección partida repite el título de la sección.** Con él, el
  trozo del ejemplo sube de 0,843 a 0,881 de similitud (medido antes de reindexar).
- **La introducción corta que precede a una sección larga se parte con ella,** en
  lugar de quedar como un chunk casi vacío que ocupa un puesto de la búsqueda (un
  chunk de 91 caracteres con solo el título de la página era el primer resultado).
- **El solape arranca en un límite de párrafo** y no a mitad de una viñeta.
- **El corte prefiere caer justo antes de una etiqueta de grupo** (`**Leasing**`,
  de las pestañas reconstruidas en la limpieza). En una primera versión el corte
  cayó dentro del grupo "Comercio exterior": su etiqueta y la primera viñeta
  quedaron en un chunk y las otras tres en el siguiente, sin etiqueta, y el modelo
  no supo a qué línea pertenecían. Ahora cada grupo viaja entero con su etiqueta.
- **No se repite un título idéntico** cuando una página lo escribe dos veces
  seguidas (51 chunks ya lo tenían; la primera versión del cambio lo subió a 245).

**Resultado**

| | Antes | Después |
|---|---|---|
| Chunks que empiezan con un título | 72 % | 99 % |
| Chunks de menos de 150 caracteres | 72 | 51 |
| Líneas del texto limpio ausentes de los chunks de su página (sin deduplicar) | 0,78 % | 0,72 % |
| "¿Qué puedo hacer en mi línea empresarial?": viñetas de la página en la respuesta | 14 de 24 | **24 de 24** |
| Preguntas de prueba (9, con respuesta verificable) | 8 de 9 | 8 de 9 |

La fila de la pregunta de prueba mide una sola pregunta, y las 9 preguntas de la
última fila las escribió el autor: son una comprobación de que no hubo retrocesos,
no una evaluación formal.

### Salida

Cada línea de `chunks.jsonl`:

```json
{
  "id": "<huella del texto>",
  "url": "https://www.bbva.com.co/personas/productos/cuentas/ahorro/blue.html",
  "titulo": "Cuenta de Ahorro Blue",
  "seccion": "personas", "categoria": "productos", "subcategoria": "cuentas",
  "orden": 2,
  "texto": "### Tasas y tarifas\n\n...",
  "repeticiones": 0
}
```

`orden` es la posición del chunk dentro de su página. El `titulo` se guarda aparte
para poder anteponerlo al texto cuando se calculen los embeddings.

## Etapa 4 — Vectorización e indexación (implementada)

`src/ingestion/indexador.py`. Entrada: `data/clean/chunks.jsonl`. Salida: la
colección `bbva` en Chroma (`data/chroma/`, ~54 MB).

### Qué hace

1. Pide a la fábrica de proveedores un generador de embeddings y una base 
   vectorial, el indexador no conoce las tecnologías concretas.
2. Descarta los chunks que ya están indexados, así que se puede
   interrumpir y reanudar.
3. Por cada lote de 128 chunks, calcula el embedding de `titulo + texto` y lo guarda
   con sus metadatos (`url`, `titulo`, `seccion`, `categoria`, `subcategoria`,
   `orden`, `repeticiones`), que permiten filtrar al recuperar.

El **título** de la página se antepone al texto al vectorizar: un chunk de mitad
de página (`### Requisitos`) no dice de qué producto habla por sí solo.

### Decisiones

- **`multilingual-e5-small`.** El contenido está en español; admite 512 tokens, que
  caben los chunks de ~1.000 caracteres (el MiniLM multilingüe solo admite 128 y
  los cortaría). Es gratuito y pequeño.
- **Prefijos `passage:` y `query:`.** e5 los exige para documentos y preguntas
  respectivamente; sin ellos la calidad baja. Están dentro de la clase.
- **Embeddings en CPU,** a propósito: la VRAM de la GPU (6 GB) se reserva para el LLM.
- **Distancia coseno** con vectores normalizados.
- **Chroma como base vectorial:**
  - Código abierto y sin costo.
  - El mismo código corre embebida (desarrollo) o como servidor (Docker); solo
    cambia `CHROMA_HOST`.
  - Guarda metadatos y filtra por ellos, algo que se aprovecha desde la limpieza
    (`seccion`, `categoria`, ...).
  - Es proporcionada al volumen (~7.700 vectores).
  - *Descartadas:* **Qdrant** (más robusta, pero más compleja de lo que este
    volumen necesita, sería la candidata si el sistema crece), **FAISS** (es una
    librería de búsqueda, no una base de datos) y **pgvector** (obliga a mantener
    un PostgreSQL solo para esto).

### Resultado

7.493 chunks indexados en unos 5 minutos en CPU.

## Patrones de diseño

| Patrón | Tipo | Dónde | Estado |
|---|---|---|---|
| **Strategy** | Comportamental | `src/ingestion/chunking.py` | Hecho |
| **Factory** | Creacional | `src/providers/factory.py` | Hecho (falta el LLM) |

### Strategy: estrategias de chunking

- **Qué es:** `Chunker` es una interfaz con un único método, `dividir(pagina)`.
  `HeadingChunker` y `FixedSizeChunker` la implementan, cada una con su propia
  forma de partir el texto.
- **Por qué aquí:** hay más de una forma razonable de dividir las páginas y no se
  sabe cuál es mejor hasta medirlo. Con Strategy se cambia con `--estrategia`
  sin tocar el resto del flujo, y ambas se pudieron comparar sobre los mismos datos.
- **Alternativa descartada:** un `if` dentro de una sola función. Funcionaría,
  pero mezclaría ambos algoritmos y obligaría a modificarla cada vez que se
  añada otra estrategia.

### Factory: proveedores

- **Qué es:** `FabricaProveedores` es una clase abstracta que define *qué* se crea
  (`crear_embeddings`, `crear_vector_store`). `FabricaLocal` define *cómo*:
  `E5Embeddings` y `ChromaVectorStore`. `obtener_fabrica(config)` elige la
  familia según `PERFIL`.
- **Por qué aquí:** el indexador (y, más adelante, el RAG) solo trabaja contra las
  interfaces de `providers/base.py`. Cambiar de proveedor es escribir otra fábrica y
  añadirla a `FABRICAS`, sin tocar el código que la usa.
- **Sobre el alcance:** hoy solo existe la familia `local`, así que la flexibilidad
  es potencial, no usada. Se eligió porque un cambio de modelo o de base
  vectorial es el cambio más probable en este sistema y la fábrica cuesta pocas
  líneas.

El scraper y la limpieza **no aplican ningún patrón de forma deliberada**: tienen
una sola fuente y un solo comportamiento, así que no hay nada que elegir ni
intercambiar, y forzar uno añadiría complejidad.

## Stack tecnológico

Lo implementado hasta ahora:

| Tecnología | Uso | Justificación |
|---|---|---|
| Python | Lenguaje | Requisito de la prueba |
| Playwright (`playwright.async_api`) | Descarga del HTML renderizado | El sitio carga contenido con JavaScript y bloquea clientes HTTP simples; hace falta un navegador real. `asyncio` permite varias pestañas en paralelo |
| `xml.etree.ElementTree` (stdlib) | Parseo del sitemap | Sin dependencias extra |
| BeautifulSoup 4 + `lxml` | Extracción y limpieza del HTML | API sencilla para recorrer y modificar el árbol HTML; `lxml` es un parser rápido y tolerante con HTML roto |
| `multilingual-e5-small` (`sentence-transformers`) | Embeddings | Multilingüe, gratuito, pequeño y con 512 tokens de contexto. Corre en CPU para dejar la VRAM al LLM |
| Chroma | Base vectorial | Código abierto, embebida o como servidor con el mismo código, filtrado por metadatos y proporcionada a ~7.700 vectores |
| `python-dotenv` | Configuración | Parámetros externalizados en `.env` sin tocar el código |

Decisión tomada, aún sin implementar:

| Tecnología | Uso | Justificación |
|---|---|---|
| Ollama + modelo local | LLM | Modelos de código abierto que corren en local, sin costo. El hardware de desarrollo es una GTX 1060 de 6 GB, que limita a modelos pequeños: 3B por defecto y 7B opcional |

La interfaz está pendiente de definir.

## Limitaciones conocidas y decisiones de diseño

- **El scraping corre fuera de Docker.** El WAF de BBVA bloquea Chrome headless,
  por lo que el scraper abre una ventana real, algo que no funciona dentro de un
  contenedor. 
- **No se espera a que la red quede inactiva** antes de capturar el HTML. En una
  prueba de 10 páginas el contenido llegó completo, pero no se garantiza para las
  1.240. La limpieza no mostró cargas incompletas generalizadas.
- **Una página bloqueada por el WAF con HTTP 200 se guardaría como válida.** Hoy
  solo se valida el código de estado.
- **Posible inconsistencia si el proceso muere** justo entre guardar el HTML y
  escribir su línea en el manifest: la URL se daría por descargada sin figurar en
  él.
- **Los datos crudos pesan ~465 MB y no se versionan** en el repositorio, porque
  agregaban demasiado peso. Sí se versionan los datos limpios y los chunks
  (`data/clean/`, unos 14 MB), así que tras clonar no hace falta scrapear: el
  scraper solo sirve para refrescar.
- **Las páginas de la limpieza son una foto de la fecha de descarga**, y el sitio
  inyecta fechas dinámicas; solo se eliminó la que acompaña a `PUBLICIDAD`.
- **Contenido repetido entre páginas.** Bloques enteros aparecen en cientos de páginas.
  La limpieza los conserva tal cual y la deduplicación se hace en el chunking.
- **La deduplicación solo detecta textos idénticos.** Dos bloques casi iguales
  se conservan ambos. Del texto repetido solo se guarda la primera URL de origen, 
  más un contador.
- **El chunking descarta fragmentos de menos de 80 caracteres** casi siempre encabezados 
  sueltos; puede caer algún texto corto real.
- **El tamaño de chunk se mide en caracteres, no en tokens.** Es una aproximación
  que se afinará al definir el prompt.
- **Cada trozo repite solo el título de su propia sección,** no la ruta completa de
  títulos superiores. Los títulos de esta web no siguen una jerarquía regular, así
  que no se intentó reconstruirla.
- **Una respuesta que abarca varios chunks depende de que todos entren en el top 5.**
  La lista de líneas empresariales ya entra completa (ocupa 3 chunks), pero una
  lista más larga podría volver a quedar incompleta.
- **La limpieza descarta páginas con menos de 200 caracteres.** Entre ellas
  algunos artículos de blog muy cortos quedan fuera.
- **Las listas pueden contener títulos.** Algunos elementos `<li>` son en realidad
  títulos de bloque (`- PORTAFOLIO BÁSICO`) y se conservan como viñeta.
- **Es una foto del sitio en un momento dado.** No hay actualización incremental.
- **Los puntajes de similitud de e5 están muy comprimidos.** No se puede usar un 
  umbral fijo para decidir "no tengo información sobre eso", habrá que resolverlo 
  en el RAG.
- **La base vectorial no se versiona** (`data/chroma/`, ~54 MB). Tras clonar hay que
  ejecutar el indexador (~5 minutos y descarga del modelo) hasta que Docker lo
  automatice.
- **Chroma en Docker exige que cliente y servidor tengan la misma versión**
  (`chromadb==1.5.9`); habrá que fijar la imagen del servidor.
- **Los embeddings se calculan en CPU.** Basta para una indexación que se hace una
  vez, pero la versión de PyTorch instalada no usa la GPU.
- **Sin pruebas automáticas.**

## Futuras mejoras

- Guardar `lastmod`, fecha de descarga y código HTTP en el manifest.
- Detectar páginas de bloqueo del WAF.
- Actualización incremental usando `lastmod`.
- Registrar las URLs fallidas en un archivo para poder auditarlas.
- Pruebas unitarias de limpieza y parseo del sitemap.
- Detectar bloques casi duplicados (no solo idénticos) y conservar todas las URLs
  donde aparece cada chunk.
- Medir el tamaño de los chunks en tokens con el tokenizador del modelo de embeddings.
- Traer, junto a cada resultado, los chunks vecinos de su misma página, para que una
  lista o un procedimiento partido no llegue incompleto.
- Reranker sobre los resultados recuperados (también ayudaría a detectar preguntas
  sin respuesta en el sitio) - agregar.
- Evaluación formal de la recuperación con un conjunto de preguntas y respuestas
  esperadas.
- Embeddings en GPU (instalando la build de PyTorch con CUDA) si el volumen crece.