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
| 5. Recuperación y generación (LLM) | Hecho |
| 6. Interfaz conversacional | Siguiente |
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
                          [5. RAG: recuperación + LLM local] ---> respuesta + fuentes
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
│   ├── config.py              # configuración desde .env                     (hecho)
│   ├── scraping/
│   │   └── scraper.py         # descarga paralela del HTML crudo             (hecho)
│   ├── ingestion/
│   │   ├── limpieza.py        # HTML crudo -> texto limpio                   (hecho)
│   │   ├── chunking.py        # páginas -> chunks (Strategy)                 (hecho)
│   │   └── indexador.py       # chunks -> embeddings -> Chroma               (hecho)
│   ├── providers/
│   │   ├── base.py            # interfaces Embeddings / VectorStore / LLM    (hecho)
│   │   ├── local.py           # e5 + Chroma + Ollama                         (hecho)
│   │   └── factory.py         # Factory de proveedores                       (hecho)
│   ├── rag/
│   │   ├── asistente.py       # fachada del RAG (Facade)                     (hecho)
│   │   ├── prompt.py          # construcción del prompt                      (hecho)
│   │   └── retriever.py       # búsqueda de fragmentos                       (hecho)
│   ├── memory/                # historial de conversaciones                  (pendiente)
│   ├── analytics/             # métricas sobre el historial                  (pendiente)
│   └── ui/                    # interfaz conversacional                      (pendiente)
└── scripts/                   # validar si son necesarios                    (pendiente)
```

## Requisitos previos

- Python 3.13.5.
- **Ollama** instalado y en ejecución (<https://ollama.com>), con el modelo de lenguaje
  descargado. Sin GPU funciona en CPU, pero es bastante más lento.
- **Google Chrome instalado**, pero solo si se va a ejecutar el scraper (paso 3,
  opcional). Se lanza con `channel="chrome"`.
- Conexión a internet para el scraper y para descargar los modelos.
- Varios GB libres en disco: el entorno virtual con PyTorch, el modelo de embeddings
  y el modelo de Ollama.

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

**Los pasos 3, 4 y 5 son opcionales para reproducir el proyecto.** El HTML crudo
(`data/raw/`) no está en el repositorio porque pesa cientos de MB, pero sí los datos
limpios y los chunks (`data/clean/`, unos 15 MB), que es lo que usan las etapas
siguientes. Solo hace falta repetirlos para refrescar los datos.

### 3. Ejecutar el scraper

Para descargar el sitio completo:

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

El formato es `jsonl`: una página por línea, para centralizar la información en un
solo archivo en lugar de miles de documentos.

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
(`data/chroma/`). La primera vez descarga el modelo. Es reanudable: omite
los chunks ya indexados.

| Argumento | Descripción |
|---|---|
| `--limit N` | Indexa solo los N primeros chunks |
| `--reiniciar` | Borra lo indexado y empieza de cero |

### 7. Descargar el modelo de lenguaje

El modelo se elige con la variable `LLM_MODEL` (por defecto, `qwen3:4b`). Se recomienda
`qwen3:4b-instruct`, que responde mucho más rápido:

```bash
ollama pull qwen3:4b-instruct
```

Después, copia `.env.example` a `.env` y cambia la línea `LLM_MODEL=qwen3:4b` por
`LLM_MODEL=qwen3:4b-instruct`.

### 8. Hacer una pregunta

```bash
python -m src.rag.asistente "¿Qué requisitos pide un crédito de vivienda?"
```

Imprime la respuesta y las páginas del sitio que se usaron como fuente. Responde una
pregunta por ejecución y no guarda historial, la interfaz conversacional es la siguiente
etapa. Cada ejecución tarda unos segundos extra porque carga el modelo de embeddings. Si
Ollama no está en ejecución o el modelo no está descargado, muestra el error y cómo
resolverlo.

### 9. Cómo usar la interfaz conversacional

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
6. Guarda cada página y registra en el manifest la relación URL → archivo.

**Salida** en `data/raw/`:

- `<hash>.html` — un archivo por página. El nombre son los primeros 16 caracteres
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

Antes de escribir reglas se analizaron los HTML crudos con ayuda de Claude (asistente
de IA). Dos mediciones guiaron el diseño:

- **Estructura:** casi todas las páginas tienen un único `<main>` y solo unas pocas no
  lo tienen; la mediana de texto es de unos 4.000 caracteres. Sobre el contenido se
  detectaron separadores `U+2028`, espacios de ancho cero `U+200B`, espacios
  duros `NBSP` y guiones suaves.
- **Ruido de interfaz:** se contó cuántas páginas repiten cada línea de texto.
  Las líneas que aparecen solas en gran parte de las páginas son botones y
  etiquetas, no contenido (`Más información`, `Anterior`, `Siguiente`, `Cerrar`,
  `1 de 1`...). Un caso llamativo: la fecha del día (`PUBLICIDAD` + fecha) la
  inyecta el sitio en la mitad de las páginas y no es contenido.

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
   delante del contenido de su panel.
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
| En el manifest | ~1.240 |
| Limpias (`paginas.jsonl`) | ~1.200 |
| Descartadas (`descartadas.jsonl`) | ~40 |

Una página se **descarta** si no tiene `<main>` o si tras limpiar le quedan
menos de 200 caracteres. Revisadas una a una, casi todas son simuladores,
formularios, buscadores y organigramas (imágenes): no tienen texto que indexar.
Cada descarte queda registrado con su motivo.

### Decisiones

- **NFC y no NFKC** al normalizar: NFKC convertiría `º` y `ª` en `o` y `a`.
- **No se usa `<body>` como alternativa** cuando falta `<main>`: arrastraría
  cabecera, pie y cookies al índice; es preferible descartar la página.
- **`lxml` como parser.** Con `html.parser` el resultado fue idéntico en todas las
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
  "Comercio exterior" o de "Leasing". Muchas páginas usan pestañas y en la mayoría
  (preguntas frecuentes) el panel repite su título y no se pierde nada, pero en unas
  decenas de páginas sí.
- **Solución:** si la etiqueta no aparece como título propio de su panel, se escribe
  en negrita (`**Comercio exterior**`) delante del contenido y se elimina la lista de
  etiquetas, que quedaba redundante.
- **La etiqueta es una línea en negrita y no un título (`####`)** a propósito: así
  todo el grupo de pestañas sigue siendo una sola sección bajo su título común, y la
  pregunta general ("¿qué puedo hacer en mi línea?") sigue encontrando el contenido.
  Con un título por pestaña, cada una sería un chunk aparte sin el título común.
- **Títulos dentro de viñetas.** Un elemento de lista cuyo título era un `<h2>`
  quedaba como `- ## Título` (cientos de líneas en muchas páginas). Ahora es `- Título`.

## Etapa 3 — Chunking (implementada)

`src/ingestion/chunking.py`. Entrada: `data/clean/paginas.jsonl`. Salida:
`data/clean/chunks.jsonl`.

### Cómo se diseñó

Igual que la limpieza, primero se midió. Al partir las páginas por encabezados salen
unas 15.000 secciones, con una mediana de unos 200 caracteres:

- Muchas son diminutas y unas pocas son enormes, con casos de miles de caracteres.
- Partir únicamente por encabezados no sirve, y partir por tamaño fijo ignora la
  estructura. Por eso se implementaron **ambas estrategias** para compararlas.
- Una parte importante del texto es un duplicado exacto de otra sección (bloques de
  FAQs de tarjetas repetidos en cientos de páginas).

### Estrategias

- **`headings` (por defecto, híbrida):** una sección de tamaño normal es un chunk;
  las secciones muy cortas (menos de 300 caracteres) se unen a la siguiente; una
  que no cabe en 1.000 caracteres se parte con solape, intentando cortar en un
  salto de párrafo o de línea y no a mitad de palabra. **Cada trozo de una sección
  partida repite el título de la sección**: sin él, los trozos de continuación no
  decían de qué trataban y la búsqueda no los encontraba. El corte también prefiere
  caer justo antes de una etiqueta de grupo (las pestañas reconstruidas en la
  limpieza), para que un grupo no quede separado de su etiqueta.
- **`fija` (línea base):** ventana de 1.000 caracteres sobre todo el texto, sin
  mirar los encabezados.

### Resultado

| | `headings` | `fija` |
|---|---|---|
| Chunks finales (después de deduplicar) | ~7.500 | ~5.900 |
| Tamaño mediano | ~600 caracteres | ~900 caracteres |
| Chunks que empiezan con un encabezado | casi todos | una minoría |

Se eligió `headings` porque sus chunks corresponden a secciones reales de la
página, lo que da fragmentos más coherentes al recuperar, antes de
deduplicar genera cerca de 9.500 chunks y descarta los de menos de 80 caracteres.

### Deduplicación

Cada chunk se identifica por una huella del texto. Si el mismo texto aparece en otra
página, se conserva solo la primera copia y se suma `repeticiones`. El caso más 
repetido, un bloque de FAQs de tarjetas, aparecía más de doscientas veces.

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

`orden` corresponde a la posición que ocupa el chunk dentro de su página. El título
se almacena por separado para poder anteponerlo al contenido al momento de calcular
los embeddings.

El diseño del chunking se desarrolló con ayuda de IA (Claude) y se validó sobre los 
datos reales.

## Etapa 4 — Vectorización e indexación (implementada)

`src/ingestion/indexador.py`. Entrada: `data/clean/chunks.jsonl`. Salida: la
colección `bbva` en Chroma (`data/chroma/`, decenas de MB).

### Qué hace

1. Pide a la fábrica de proveedores un generador de embeddings y una base
   vectorial; el indexador no conoce las tecnologías concretas.
2. Descarta los chunks que ya están indexados, así que se puede
   interrumpir y reanudar.
3. Por cada lote de 128 chunks, calcula el embedding de `titulo + texto` y lo guarda
   con sus metadatos (`url`, `titulo`, `seccion`, `categoria`, `subcategoria`,
   `orden`, `repeticiones`), que permiten filtrar al recuperar.

El **título** de la página se antepone al texto al vectorizar: un chunk de mitad
de página (`### Requisitos`) no dice de qué producto habla por sí solo.

### Decisiones

- **`multilingual-e5-small`.** El contenido está en español; admite 512 tokens, que
  caben los chunks de ~1.000 caracteres, y es gratuito y pequeño.
- **Prefijos `passage:` y `query:`.** e5 los exige para documentos y preguntas
  respectivamente; sin ellos la calidad baja. Están dentro de `E5Embeddings`.
- **Embeddings en CPU,** a propósito: la VRAM de la GPU (6 GB) se reserva para el LLM.
- **Distancia coseno** con vectores normalizados.
- **Chroma como base vectorial:**
  - Código abierto y sin costo.
  - El mismo código corre embebida o como servidor (Docker); solo
    cambia `CHROMA_HOST`.
  - Guarda metadatos y filtra por ellos: `seccion`, `categoria` y `subcategoria` se
    generan en la limpieza y permiten restringir la búsqueda.
  - Es proporcionada al volumen (unos miles de vectores).
  - *Descartadas:* **Qdrant** (más robusta, pero más compleja de lo que este
    volumen necesita, sería la candidata si el sistema crece), **FAISS** (es una
    librería de búsqueda, no una base de datos) y **pgvector** (obliga a mantener
    un PostgreSQL solo para esto).

### Resultado

Unos 7.500 chunks indexados en pocos minutos en CPU.

## Etapa 5 — Recuperación y generación (implementada)

`src/rag/` (`retriever.py`, `prompt.py`, `asistente.py`) y `OllamaLLM` en
`src/providers/local.py`. Entrada: una pregunta y, opcionalmente, el historial de la
conversación. Salida: la respuesta y las páginas del sitio que se usaron como fuente.

### Qué hace

1. **Recupera.** `Retriever` convierte la pregunta en un embedding (con el prefijo
   `query:`) y pide a Chroma los fragmentos más parecidos (`TOP_K`, por defecto 5).
   Admite un filtro por metadatos (`seccion`, `categoria`...), que hoy no se usa.
2. **Arma el prompt.** `construir_mensajes` compone la conversación en formato de chat:
   las instrucciones del sistema, el historial previo y un último mensaje con los
   fragmentos numerados (título, URL y texto) seguidos de la pregunta.
3. **Genera.** `OllamaLLM` envía los mensajes al modelo local de Ollama y devuelve
   su respuesta.
4. **Responde.** `AsistenteRAG.responder` (la fachada) devuelve el texto y una fuente
   por página, con el mejor puntaje de sus fragmentos.

### El prompt

Las instrucciones del sistema piden al modelo que:

- responda solo con la información de los fragmentos entregados;
- si no la encuentra, diga exactamente *"No encontré esa información en el sitio de
  BBVA Colombia."* en lugar de inventar cifras, tasas o requisitos;
- si el usuario solo saluda o se despide, responda con un saludo breve;
- responda en español, de forma clara y breve, citando el título de la página entre
  corchetes;
- use la conversación previa para entender las preguntas de seguimiento.

La regla del saludo se añadió después de probar: sin ella, un simple "hola" recibía
"No encontré esa información".

### Decisiones

- **Ollama con un modelo local.** Es gratuito, no depende de una API externa y corre en
  el equipo de desarrollo (una GTX 1060 de 6 GB), lo que limita a modelos pequeños
  (~4B parámetros).
- **Contexto de 4.096 tokens (`LLM_NUM_CTX`) fijado explícitamente.** Si el prompt no
  cabe, Ollama lo recorta en silencio; un prompt típico con cinco fragmentos ronda los
  mil tokens, así que queda margen para el historial.
- **Temperatura baja (0,2)**, para respuestas estables y apegadas al contexto.
- **Razonamiento desactivado.** Los modelos que "piensan" antes de responder gastan
  mucho tiempo y tokens. Se pide desactivarlo (`think=False`); si el modelo no admite la
  opción, se reintenta sin ella y se recuerda para no repetir el intento fallido. Algunos
  modelos, como la variante *thinking* de Qwen3, razonan igualmente y devuelven el
  razonamiento dentro de la respuesta, cerrado solo por `</think>`: se descarta todo lo
  anterior a esa etiqueta.
- **Errores con instrucciones.** Si Ollama no responde o el modelo no está descargado,
  se lanza un error que dice cómo resolverlo (`ollama serve`, `ollama pull <modelo>`)
  en lugar de un mensaje técnico.

### Elección del modelo

Se compararon dos variantes de Qwen3 de 4B con las mismas preguntas, el mismo
retriever y el mismo prompt: `qwen3:4b`, que razona siempre antes de responder, y
`qwen3:4b-instruct`, que responde directamente.

| | `qwen3:4b-instruct` | `qwen3:4b` |
|---|---|---|
| Tiempo por respuesta | unos segundos | de decenas de segundos a más de un minuto |
| Calidad en las preguntas de prueba | similar | similar |

Ambas acertaron la mayoría de las preguntas y fallaron en preguntas distintas. La
diferencia real está en la velocidad, así que se recomienda `qwen3:4b-instruct`.
**El valor por defecto del código sigue siendo `qwen3:4b`**; para usar el recomendado
hay que cambiar `LLM_MODEL` (paso 7).

Las preguntas de prueba son pocas y las escribió el autor: datos concretos de
productos, preguntas sin relación con el sitio, un saludo y una pregunta de
seguimiento. Sirven para comprobar que no hay retrocesos y para elegir modelo, pero no
son una evaluación formal.

### Resultado

El asistente responde con datos concretos del sitio (cuotas, edades, teléfonos, pasos
de un trámite) y cita la página de donde salen. Rechaza las preguntas sin relación con
el sitio y responde a los saludos.

Probarlo con preguntas reales también sirvió para depurar las etapas anteriores: la
pregunta *"¿Qué puedo hacer en mi línea empresarial?"* devolvía una lista incompleta, lo
que llevó a corregir la reconstrucción de pestañas en la limpieza y el título repetido
en el chunking (ver arriba).

## Patrones de diseño

| Patrón | Tipo | Dónde | Estado |
|---|---|---|---|
| **Strategy** | Comportamental | `src/ingestion/chunking.py` | Hecho |
| **Factory** | Creacional | `src/providers/factory.py` | Hecho |
| **Facade** | Estructural | `src/rag/asistente.py` | Hecho |

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
  (`crear_embeddings`, `crear_vector_store`, `crear_llm`). `FabricaLocal` define
  *cómo*: `E5Embeddings`, `ChromaVectorStore` y `OllamaLLM`. `obtener_fabrica(config)`
  elige la familia según `PERFIL`.
- **Por qué aquí:** el indexador y el RAG solo trabajan contra las interfaces de
  `providers/base.py`. Cambiar de proveedor es escribir otra fábrica y añadirla a
  `FABRICAS`, sin tocar el código que la usa.
- **Sobre el alcance:** hoy solo existe la familia `local`, así que la flexibilidad
  es potencial, no usada. Se eligió porque un cambio de modelo o de base
  vectorial es el cambio más probable en este sistema y la fábrica cuesta pocas
  líneas.

### Facade: asistente RAG

- **Qué es:** `AsistenteRAG` (`src/rag/asistente.py`) esconde el flujo RAG completo
  tras un único método, `responder(pregunta, historial)`: recupera los fragmentos
  (`Retriever`), arma el prompt (`construir_mensajes`), llama al LLM y devuelve una
  `Respuesta` con el texto y las fuentes (una por página). `AsistenteRAG.desde_config()`
  lo construye con los proveedores que entrega la fábrica.
- **Por qué aquí:** responder una pregunta encadena tres piezas distintas (búsqueda
  vectorial, prompt y LLM). Quien use el asistente (el CLI `python -m src.rag.asistente`
  y, más adelante, la interfaz de chat) solo necesita `responder`. Así, cambiar algo
  dentro del flujo (otro modelo, un reranker, reescribir la pregunta con el historial)
  no obliga a tocar a quien lo llama.
- **Alternativa descartada:** que cada interfaz encadene retriever, prompt y LLM por
  su cuenta. Funcionaría, pero cada una repetiría esos pasos y cualquier cambio del
  flujo habría que replicarlo en todas.
- **Sobre el alcance:** la fachada no guarda el historial: lo recibe como parámetro
  (`historial`, una lista de mensajes `{"role", "content"}`). Guardarlo por
  `session_id` es una etapa aparte, todavía pendiente.

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
| `multilingual-e5-small` (`sentence-transformers`) | Embeddings | Multilingüe, gratuito, pequeño y con 512 tokens de contexto; corre en CPU para dejar la VRAM al LLM |
| Chroma | Base vectorial | Código abierto, embebida o como servidor con el mismo código, filtrado por metadatos |
| `python-dotenv` | Configuración | Parámetros externalizados en `.env` sin tocar el código |
| Ollama + `qwen3:4b-instruct` (cliente `ollama`) | LLM | Modelo de código abierto que corre en local, sin costo ni API externa. El hardware de desarrollo es una GTX 1060 de 6 GB, que limita a modelos pequeños. Se recomienda la variante *instruct*, mucho más rápida que la que razona |

La interfaz está pendiente de definir.

## Limitaciones conocidas y decisiones de diseño

- **El scraping corre fuera de Docker.** El WAF de BBVA bloquea Chrome headless,
  por lo que el scraper abre una ventana real, algo que no funciona dentro de un
  contenedor.
- **No se espera a que la red quede inactiva** antes de capturar el HTML. En una
  prueba de 10 páginas el contenido llegó completo, pero no se garantiza para todas.
  La limpieza no mostró cargas incompletas generalizadas.
- **Una página bloqueada por el WAF con HTTP 200 se guardaría como válida.** Hoy
  solo se valida el código de estado.
- **Posible inconsistencia si el proceso muere** justo entre guardar el HTML y
  escribir su línea en el manifest: la URL se daría por descargada sin figurar en
  él.
- **Los datos crudos pesan cientos de MB y no se versionan** en el repositorio, porque
  agregaban demasiado peso. Sí se versionan los datos limpios y los chunks
  (`data/clean/`, unos 15 MB), así que tras clonar no hace falta scrapear: el
  scraper solo sirve para refrescar.
- **Las páginas de la limpieza son una foto de la fecha de descarga**, y el sitio
  inyecta fechas dinámicas; solo se eliminó la que acompaña a `PUBLICIDAD`.
- **Contenido repetido entre páginas.** Bloques enteros aparecen en cientos de páginas.
  La limpieza los conserva tal cual y la deduplicación se hace en el chunking.
- **La deduplicación solo detecta textos idénticos.** Dos bloques casi iguales
  se conservan ambos. Del texto repetido solo se guarda la primera URL de origen,
  más un contador.
- **El chunking descarta fragmentos de menos de 80 caracteres**, casi siempre
  encabezados sueltos; puede caer algún texto corto real.
- **El tamaño de chunk se mide en caracteres, no en tokens.** Es una aproximación
  que se afinará al definir el prompt.
- **La limpieza descarta páginas con menos de 200 caracteres.** Entre ellas
  algunos artículos de blog muy cortos quedan fuera.
- **Las listas pueden contener títulos.** Algunos elementos `<li>` son en realidad
  títulos de bloque (`- PORTAFOLIO BÁSICO`) y se conservan como viñeta.
- **Es una foto del sitio en un momento dado.** No hay actualización incremental.
- **Los puntajes de similitud de e5 están muy comprimidos.** No se puede usar un
  umbral fijo para decidir "no tengo información sobre eso", así que el rechazo de
  preguntas sin relación con el sitio se delega en las instrucciones del prompt.
- **La base vectorial no se versiona** (`data/chroma/`, decenas de MB). Tras clonar hay
  que ejecutar el indexador (unos minutos y descarga del modelo) hasta que Docker lo
  automatice.
- **Chroma en Docker exige que cliente y servidor tengan la misma versión**
  (`chromadb==1.5.9`); habrá que fijar la imagen del servidor.
- **Los embeddings se calculan en CPU.** Basta para una indexación que se hace una
  vez, pero la versión de PyTorch instalada no usa la GPU.
- **Las preguntas de seguimiento no usan el historial al buscar.** El historial llega
  al modelo, pero la búsqueda se hace con la pregunta suelta: algo como "¿y la del plan
  plus?" no sabe de qué producto se habla.
- **El modelo puede quedarse con un fragmento poco adecuado** cuando el correcto no
  queda entre los primeros resultados de la búsqueda.
- **Las fuentes que se muestran son las recuperadas**, aunque la pregunta no tenga
  relación con el sitio (por ejemplo, un saludo).
- **Una respuesta que abarca varios chunks depende de que todos entren** entre los
  fragmentos recuperados; una lista muy larga podría llegar incompleta.
- **La interfaz actual responde una pregunta por ejecución** y vuelve a cargar el
  modelo de embeddings cada vez.
- **Ollama debe estar en ejecución.** Sin GPU el modelo corre en CPU, bastante más lento.
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
- Reranker sobre los resultados recuperados (también ayudaría a detectar preguntas
  sin respuesta en el sitio).
- Reescribir las preguntas de seguimiento con el historial antes de buscar.
- Traer, junto a cada resultado, los chunks vecinos de su misma página, para que una
  lista o un procedimiento partido no llegue incompleto.
- Evaluación formal de la recuperación y de los modelos con un conjunto de preguntas y
  respuestas esperadas, para comparar también otros modelos pequeños (por ejemplo,
  Granite, Ministral o Qwen3.5) y otros embeddings.
- Mostrar las fuentes solo cuando la respuesta las use.
- Embeddings en GPU (instalando la build de PyTorch con CUDA) si el volumen crece.