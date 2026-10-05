# Asistente BBVA — Sistema RAG con Web Scraping

Asistente conversacional que responde preguntas sobre el contenido del sitio
público de BBVA Colombia (<https://www.bbva.com.co/>) usando RAG. Prueba técnica de Machine Learning Engineer.

## Estado del proyecto

| Etapa | Estado |
|---|---|
| 1. Scraping: descarga del HTML crudo | Hecho |
| 2. Limpieza y normalización del HTML | Hecho |
| 3. Chunking | Hecho |
| 4. Vectorización e indexación | Hecho |
| 5. Recuperación y generación (LLM) | Hecho |
| 6. Historial de conversación por ID | Hecho |
| 7. Interfaz conversacional | Hecho |
| 8. Análisis del historial (métricas) | Hecho |
| 9. Dockerización | Hecho |

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
                                          ^
                                          |
                          [6. CHAT: historial por sesión + preguntas de seguimiento] ---> data/historial/
                                          ^
                                          |
                          [7. API web (FastAPI) + página de chat] <--- usuario

data/historial/ ---> [8. ANÁLISIS: métricas del historial] ---> reporte en pantalla
```

Las etapas están separadas a propósito: el scraper solo descarga y guarda HTML
sin transformarlo. Toda la limpieza ocurre después, a partir de los datos crudos.
Así se puede corregir o cambiar la limpieza sin volver a scrapear el sitio.

## Estructura del repositorio - pensada inicialmente

```
Asistente_BBVA/
├── Dockerfile                 # imagen de la aplicación
├── docker-compose.yml         # todos los servicios con un solo comando
├── docker-compose.gpu.yml     # añade la GPU NVIDIA al servicio de Ollama
├── data/
│   ├── raw/                   # HTML crudo + manifest.jsonl 
│   ├── clean/                 # paginas, descartadas y chunks 
│   ├── chroma/                # base vectorial local 
│   └── historial/             # conversaciones en SQLite 
├── src/
│   ├── config.py              # configuración desde .env
│   ├── scraping/
│   │   └── scraper.py         # descarga paralela del HTML crudo
│   ├── ingestion/
│   │   ├── limpieza.py        # HTML crudo -> texto limpio
│   │   ├── chunking.py        # páginas -> chunks (Strategy)
│   │   └── indexador.py       # chunks -> embeddings -> Chroma
│   ├── providers/
│   │   ├── base.py            # interfaces Embeddings / VectorStore / LLM
│   │   ├── local.py           # e5 + Chroma + Ollama
│   │   └── factory.py         # Factory de proveedores
│   ├── rag/
│   │   ├── asistente.py       # fachada del RAG (Facade)
│   │   ├── chat.py            # servicio de conversación (historial + RAG)
│   │   ├── prompt.py          # construcción del prompt
│   │   └── retriever.py       # búsqueda de fragmentos
│   ├── memory/
│   │   └── historial.py       # historial por sesión (Repository, SQLite)
│   ├── analytics/
│   │   └── metricas.py        # métricas del historial (cálculo y comando)
│   └── ui/
│       ├── api.py             # API web (FastAPI)
│       └── static/index.html  # página de chat
└── tests/
    ├── test_metricas.py       # pruebas de las métricas del historial
    └── test_chat.py           # pruebas del servicio de chat
```

## Requisitos previos

Para levantar el sistema con Docker (lo recomendado):

- **Docker con Compose v2.24 o superior.** En Windows y macOS, Docker Desktop en Linux, Docker 
  Engine con el plugin de Compose.
- **Unos 15 GB libres en disco:** las imágenes y los dos modelos se descargan la primera vez.
- Conexión a internet la primera vez.
- Opcional: una **GPU NVIDIA**, para que el modelo de lenguaje responda más rápido 

Para ejecutarlo sin Docker (desarrollo, y para el scraper):

- Python 3.13.5.
- **Ollama** instalado y en ejecución (<https://ollama.com>), con el modelo de lenguaje
  descargado. Sin GPU funciona en CPU, pero es bastante más lento.
- **Google Chrome instalado**, pero solo si se va a ejecutar el scraper (paso 3 de la
  ejecución local, opcional). Se lanza con `channel="chrome"`.
- Conexión a internet para el scraper y para descargar los modelos.
- Varios GB libres en disco: el entorno virtual con PyTorch, el modelo de embeddings
  y el modelo de Ollama.

Las variables de entorno son opcionales: todo tiene un valor
por defecto y `.env.example` lista los parámetros (cópialo a `.env` para cambiarlos).

## Instrucciones paso a paso

### 1. Clonar el repositorio

```bash
git clone https://github.com/andresgarces834/Asistente_BBVA
cd Asistente_BBVA
```

### 2. Configurar (opcional)

No hace falta para probarlo. Para cambiar algún parámetro, copia `.env.example` a `.env` 
y edita las líneas que quieras:
Docker lo lee solo. Lo único que Docker fija por su cuenta son las direcciones de los
servicios. Si el puerto 8000 de tu equipo ya está ocupado, pon por ejemplo `API_PORT=8001`
en el `.env` y abre la interfaz en ese puerto.

### 3. Levantar el sistema

```bash
docker compose up --build
```

Con una GPU NVIDIA, añade el archivo de la GPU para que el modelo de lenguaje la use. Sin
ella el modelo corre en CPU y cada respuesta tarda alrededor de un minuto; con la GPU, unos
segundos:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
```

Es un solo comando y levanta todo. **La primera vez tarda bastante:**
descarga las imágenes y los dos modelos y después indexa el sitio. Los arranques
siguientes son mucho más rápidos, porque lo descargado y lo indexado se conserva. El
sistema está listo cuando el registro muestra `Uvicorn running on http://0.0.0.0:8000`.

### 4. Usar la interfaz de chat

Abre <http://localhost:8000> en el navegador.

- Escribe una pregunta o elige una de las sugerencias. Bajo cada respuesta, **Fuentes**
  muestra las páginas del sitio que se usaron.
- La conversación tiene un **ID**, que se ve arriba y el navegador recuerda. **Nueva**
  empieza otra conversación y **Cargar ID** vuelve a una anterior.
- Las preguntas de seguimiento se entienden gracias al historial, y bajo cada respuesta se
  ve con qué pregunta se buscó.

La documentación interactiva de la API está en <http://localhost:8000/docs>.

### 5. Analizar el historial

```bash
docker compose exec app python -m src.analytics.metricas
```

### 6. Detener el sistema

```bash
docker compose down
```

Detiene los contenedores y conserva los datos: la base vectorial, los modelos y las
conversaciones están en volúmenes. Para borrarlos también, `docker compose down -v`.

## Ejecución local, sin Docker

Sirve para desarrollar y es la única forma de ejecutar el scraper. Necesita Python, Ollama
y las dependencias instaladas.

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

El modelo se elige con la variable `LLM_MODEL`. Por defecto es `qwen3:4b-instruct`, que
responde mucho más rápido que las variantes que razonan antes de contestar:

```bash
ollama pull qwen3:4b-instruct
```

Para usar otro modelo, descárgalo del mismo modo, copia `.env.example` a `.env` y cambia
la línea `LLM_MODEL`.

### 8. Hacer una pregunta por terminal

```bash
python -m src.rag.asistente "¿Qué requisitos pide un crédito de vivienda?"
```

Imprime la respuesta y las páginas del sitio que se usaron como fuente. Responde una
pregunta por ejecución y no guarda historial; para conversar usa la interfaz web.
Cada ejecución vuelve a cargar el modelo de embeddings, lo que añade un rato de espera. Si
Ollama no está en ejecución o el modelo no está descargado, muestra el error y cómo
resolverlo.

### 9. Usar la interfaz de chat

```bash
python -m src.ui.api
```

Al arrancar carga los modelos, así que tarda en estar lista. Después abre
<http://127.0.0.1:8000> en el navegador (la dirección y el puerto se cambian con
`API_HOST` y `API_PORT`).

- Escribe una pregunta o elige una de las sugerencias. Bajo cada respuesta, **Fuentes**
  muestra las páginas del sitio que se usaron.
- La conversación tiene un **ID**, que se ve arriba y el navegador recuerda. **Nueva**
  empieza otra conversación y **Cargar ID** vuelve a una anterior; al recargar la página
  también se recupera.
- Las preguntas de seguimiento se entienden gracias al historial. Bajo cada respuesta 
  se ve con qué pregunta se buscó.
- Cuántos mensajes previos se tienen en cuenta se configura con `N_MENSAJES` (6 por
  defecto). Las conversaciones se guardan en `data/historial/historial.db`.

La documentación interactiva de la API está en `/docs`.

### 10. Analizar el historial

```bash
python -m src.analytics.metricas
```

Recorre todas las conversaciones guardadas y muestra el número de conversaciones, los
mensajes por conversación, los turnos usuario-asistente, la longitud promedio de los
mensajes y la duración de las conversaciones. Solo lee el historial y no necesita Ollama.
Con `--db RUTA` analiza otro archivo SQLite; sin ella usa el de `HISTORIAL_PATH`.

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
diferencia real está en la velocidad, así que `qwen3:4b-instruct` es el modelo por
defecto. Se puede cambiar con la variable `LLM_MODEL`, en el `.env`.

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
en el chunking.

## Etapa 6 — Historial por ID y preguntas de seguimiento (implementada)

`src/memory/historial.py`, `src/rag/chat.py` y el paso de reescritura de
`src/rag/asistente.py`. Entrada: una pregunta con el ID de su conversación. Salida: la
respuesta y el intercambio queda guardado.

### Qué hace

1. **Carga el contexto.** `ServicioChat` pide al historial los últimos `N_MENSAJES`
   mensajes de esa conversación (6 por defecto). Cuenta mensajes, no turnos, y la
   ventana siempre empieza en un mensaje del usuario, no a mitad de un intercambio.
2. **Reescribe la pregunta.** Si hay historial, el asistente la convierte en una que se
   entienda sola antes de buscar.
3. **Responde** con la fachada, pasándole ese historial para armar el prompt.
4. **Guarda** la pregunta y la respuesta. Si el modelo falla no se guarda nada, para que
   la conversación no quede con una pregunta sin respuesta.

### Por qué hace falta reescribir

La búsqueda solo ve la pregunta, no el historial: *"¿Y la del portafolio plus?"* no dice
de qué producto habla, y devolvía "no encontré" aunque la respuesta estuviera en el sitio.
Ahora el modelo la reformula con ayuda de los mensajes previos y esa versión es la que se 
usa para buscar. La pregunta original sigue siendo la que se contesta.

- Cuesta una llamada corta extra al modelo, de menos de un segundo con el modelo por
  defecto, y solo cuando hay historial.
- Si el modelo devuelve algo inservible, se usa la pregunta original.
- Se puede desactivar con `REESCRIBIR_PREGUNTAS=false`.
- La reescritura se guarda y la interfaz la muestra ("Buscado como..."), para poder ver
  cuándo el modelo interpretó mal.

### Qué se guarda

Una fila por mensaje en SQLite (`data/historial/historial.db`, ruta en `HISTORIAL_PATH`).
En las respuestas se guardan, además del texto, los datos que servirán para el análisis
del uso:

| Campo | Contenido |
|---|---|
| `session_id`, `rol`, `contenido`, `creado_en` | La conversación, en orden |
| `fuentes` | Páginas citadas (título, URL y puntaje) |
| `modelo`, `latencia_ms` | Qué modelo respondió y cuánto tardó |
| `sin_respuesta` | Si respondió que no encontró la información |
| `pregunta_reescrita` | Con qué pregunta se buscó, si hubo reescritura |

### Decisiones

- **SQLite.** Viene con Python, no necesita un servidor y un solo archivo basta para este
  volumen. Es la implementación local de `Historial`.
- **El servicio atiende de una en una**, hay un solo modelo y una sola
  GPU, y así cada intercambio se guarda completo y en orden.
- **La fachada sigue sin guardar estado:** quien lleva el historial es `ServicioChat`.
- **Esquema pensado para el análisis.** Guardar desde ya los campos de arriba permite
  calcular después las métricas con consultas simples.

### Resultado

Tras preguntar por la cuota del portafolio básico de una cuenta, *"¿Y la del portafolio 
plus?"* responde con el dato correcto. La conversación sobrevive a reiniciar el servidor, 
y se probó con varias escrituras simultáneas sin perder filas.

## Etapa 7 — Interfaz conversacional (implementada)

`src/ui/api.py` (FastAPI) y `src/ui/static/index.html` (página de chat). Se arranca con
`python -m src.ui.api`.

### Qué hace

Una página de chat que habla con una API. Al arrancar, el servidor carga los modelos y los
calienta, para que la primera pregunta no espere.

| Rutas | Para qué |
|---|---|
| `GET /` | La página de chat |
| `POST /api/chat` | Recibe una pregunta (`session_id`, `pregunta`) y devuelve la respuesta con sus fuentes |
| `GET /api/sesiones/{id}/mensajes` | Los mensajes de una conversación, para mostrarla de nuevo |
| `GET /api/salud` | Si el modelo está disponible y cuántos fragmentos hay indexados |
| `GET /docs` | Documentación interactiva de la API |

### Decisiones

- **FastAPI y una sola página HTML con JavaScript sin librerías.** Es lo más simple, no necesita
  internet ni un paso de compilación, y se sirve igual dentro de Docker.
- **Validación de entrada.** La pregunta debe tener entre 1 y 1000 caracteres y el ID solo
  admite letras, números, guion y guion bajo; si no, la API responde 422.
- **Errores que ayudan.** Si Ollama no responde o el modelo no está descargado, la API
  responde 503 con las instrucciones para resolverlo, y la página las muestra. Cualquier
  otro fallo devuelve un 500 genérico.
- **Texto seguro.** La página escapa todo el texto antes de darle formato (listas y
  negritas), así que lo que escriba el usuario o genere el modelo no puede inyectar HTML.
- **Las fuentes van plegadas** bajo cada respuesta, y una respuesta de "no encontré" no
  muestra fuentes.

### Cómo se comprobó

- Con un servicio simulado, la API: respuestas válidas, validaciones, errores 503 y 500,
  historial y estado de salud.
- En el navegador, con el servidor y los modelos reales: una conversación con pregunta de
  seguimiento, recargar la página y recuperar la conversación, empezar una nueva, una
  pregunta sin relación con el sitio, la vista en móvil y en tema claro, y el mensaje de
  error cuando el servidor no está.

## Etapa 8 — Análisis del historial (implementada)

`src/analytics/metricas.py`. Entrada: el historial de conversaciones. Salida: un reporte en
pantalla. Se ejecuta con `python -m src.analytics.metricas`.

### Qué hace

Recorre **todas** las conversaciones guardadas (`Historial.todos()`), las agrupa por ID de
sesión y calcula cinco métricas:

| Métrica | Cómo se calcula |
|---|---|
| Conversaciones | Cuántos IDs de sesión distintos hay |
| Mensajes por conversación | Mensajes del usuario y del asistente de cada conversación: promedio, mínimo y máximo |
| Turnos usuario-asistente | Una pregunta seguida de su respuesta es un turno: total, promedio por conversación y máximo |
| Longitud promedio de los mensajes | En caracteres, por separado para el usuario y para el asistente |
| Duración de la conversación | Tiempo entre su primer y su último mensaje: promedio y máxima |

### Decisiones

- **La longitud se calcula por rol.** Un solo promedio mezclaría preguntas cortas con
  respuestas largas y no diría nada de ninguna de las dos.
- **La pregunta se guarda con la hora en que llegó.** Antes, la pregunta y su respuesta
  quedaban con la misma hora (la de terminar la respuesta), y una conversación de un solo
  turno habría durado cero segundos. Las conversaciones guardadas antes de este cambio
  conservan las horas antiguas: su duración no incluye lo que tardó la primera respuesta.
- **El cálculo no sabe de SQLite.** `calcular` trabaja con mensajes; los recibe de
  `Historial.todos()`, la parte del repositorio que recorre todas las conversaciones.
- **Solo lee el historial** y no añade dependencias.

### Cómo se comprobó

Pruebas automáticas con datos inventados a mano, de modo que cada resultado esperado sale de
una cuenta sencilla (`python -m unittest discover tests`); no necesitan Ollama ni el índice.
Para ver que detectan errores se rompió el código a propósito en una copia (contar mal los
turnos, mezclar los roles, perder el orden de los mensajes...) y alguna prueba falló en
cada caso.

## Etapa 9 — Dockerización (implementada)

`Dockerfile`, `docker-compose.yml`, `docker-compose.gpu.yml` y `.dockerignore`. Un solo
comando, `docker compose up --build`, levanta el sistema completo.

### Qué hace

Compose arranca cinco servicios:

| Servicio | Qué es | Termina |
|---|---|---|
| `chroma` | Base vectorial: imagen oficial de Chroma, con la versión fijada | No: sigue en ejecución |
| `ollama` | Servidor del modelo de lenguaje: imagen oficial de Ollama | No: sigue en ejecución |
| `modelo` | Descarga el modelo de lenguaje en Ollama, solo si falta | Sí, al terminar la descarga |
| `indexador` | Calcula los embeddings de `data/clean/chunks.jsonl` y los guarda en Chroma | Sí; en los arranques siguientes omite lo ya indexado |
| `app` | La interfaz de chat y la API (puerto 8000) | No: sigue en ejecución |

`app` espera a que `chroma` responda, a que el modelo esté descargado y a que la base esté
indexada: ese orden lo fija `depends_on`. Solo `app` publica un puerto en el equipo.

```
navegador --> app --> ollama        (el modelo lo descarga `modelo`)
               |
               +----> chroma <---- indexador <---- data/clean/chunks.jsonl
```

### Decisiones

- **Un servicio por pieza, con imágenes oficiales.** Chroma y Ollama usan las suyas; solo
  la aplicación tiene `Dockerfile`. Es lo que pide el enunciado y cada pieza se puede 
  reiniciar o cambiar por separado.
- **`app` e `indexador` comparten imagen:** es el mismo código con otro comando.
- **PyTorch solo para CPU.** El paquete por defecto trae las librerías de CUDA y pesa varios
  GB; los embeddings se calculan en CPU de todos modos.
- **El modelo de lenguaje se descarga con un servicio, no al construir la imagen.** Es muy
  grande y no es código. Se guarda en un volumen y, si ya está, el servicio no hace nada.
- **La versión de Chroma está fijada** a la del cliente (`chromadb==1.5.9`): con versiones
  distintas el cliente se niega a conectarse. Al actualizar `requirements.txt` hay que
  cambiar también la imagen en `docker-compose.yml`.
- **Los datos viven en volúmenes** y sobreviven a `docker compose down`. El historial usa un
  volumen y no una carpeta del equipo porque SQLite en modo WAL no es fiable sobre las
  carpetas que Docker Desktop comparte con Windows o macOS.
- **Los datos limpios se montan, no se copian a la imagen** (`data/clean/`, solo lectura):
  se pueden refrescar sin reconstruir nada.
- **La configuración sigue externalizada.** Compose lee el `.env` si existe, igual que sin
  Docker. Solo las direcciones de los servicios las fija `docker-compose.yml`, porque en el
  `.env` apuntan a `localhost`, que dentro de un contenedor no sirve.
- **La GPU es opcional y va en otro archivo** (`docker-compose.gpu.yml`). Pedirla en el
  archivo principal haría que Docker falle en cualquier equipo sin NVIDIA. Sin ella el
  modelo corre en CPU, bastante más lento.
- **Usuario sin privilegios** dentro de la imagen de la aplicación, y los puertos de Chroma
  y Ollama no se publican: así tampoco chocan con un Ollama que ya esté instalado en el
  equipo.

### Cómo se comprobó

Con Docker Desktop en Windows, partiendo de cero (sin imágenes ni volúmenes del proyecto):

- **Arranque completo con un solo comando.** Los servicios arrancan en el orden previsto:
  Chroma y Ollama pasan su healthcheck, se descarga el modelo, el indexador indexa los
  chunks y termina, y solo entonces arranca la aplicación.
- **Una conversación real** con pregunta y seguimiento, a través de la API dentro del
  contenedor: la respuesta es correcta y el seguimiento se reescribe bien.
- **Persistencia.** La conversación sobrevive a reiniciar la aplicación y a un
  `docker compose down` seguido de `up`.
- **Segundo arranque.** No vuelve a descargar el modelo ni a indexar, y la aplicación está
  lista en menos de un minuto, frente a varios minutos la primera vez.
- **GPU.** Con `docker-compose.gpu.yml` el modelo se ejecuta entero en la GPU y las
  respuestas pasan de casi un minuto a unos diez segundos.
- **Configuración.** Un `.env` copiado de `.env.example` cambia los parámetros (se probó con
  `N_MENSAJES` y `API_PORT`) sin romper las direcciones de los servicios.
- **Dentro de la imagen:** la aplicación corre con un usuario sin privilegios, y funcionan
  las pruebas automáticas (`docker compose run --rm --no-deps app python -m unittest discover tests`)
  y el comando de métricas (`docker compose exec app python -m src.analytics.metricas`).

## Patrones de diseño

| Patrón | Tipo | Dónde | Estado |
|---|---|---|---|
| **Strategy** | Comportamental | `src/ingestion/chunking.py` | Hecho |
| **Factory** | Creacional | `src/providers/factory.py` | Hecho |
| **Facade** | Estructural | `src/rag/asistente.py` | Hecho |
| Repository | Acceso a datos | `src/memory/historial.py` | Hecho |

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
  (`crear_embeddings`, `crear_vector_store`, `crear_llm`, `crear_historial`).
  `FabricaLocal` define *cómo*: `E5Embeddings`, `ChromaVectorStore`, `OllamaLLM` y
  `HistorialSQLite`. `obtener_fabrica(config)` elige la familia según `PERFIL`.
- **Por qué aquí:** el indexador, el RAG y el servicio de chat solo trabajan contra
  interfaces. Cambiar de proveedor es escribir otra fábrica y añadirla a `FABRICAS`, sin
  tocar el código que la usa.
- **Sobre el alcance:** hoy solo existe la familia `local`, así que la flexibilidad
  es potencial, no usada. Se eligió porque un cambio de modelo o de base
  vectorial es el cambio más probable en este sistema y la fábrica cuesta pocas
  líneas.

### Facade: asistente RAG

- **Qué es:** `AsistenteRAG` (`src/rag/asistente.py`) esconde el flujo RAG completo
  tras un único método, `responder(pregunta, historial)`: reescribe la pregunta si hay
  historial, recupera los fragmentos (`Retriever`), arma el prompt (`construir_mensajes`),
  llama al LLM y devuelve una `Respuesta` con el texto y las fuentes (una por página).
  `AsistenteRAG.desde_config()` lo construye con los proveedores que entrega la fábrica.
- **Por qué aquí:** responder una pregunta encadena varias piezas distintas (reescritura,
  búsqueda vectorial, prompt y LLM). Quien use el asistente (el CLI
  `python -m src.rag.asistente` y `ServicioChat`, que alimenta la interfaz web) solo
  necesita `responder`. Así, cambiar algo dentro del flujo (otro modelo, un reranker) no
  obliga a tocar a quien lo llama: la reescritura de preguntas se añadió dentro de la
  fachada y el CLI siguió funcionando sin cambios.
- **Alternativa descartada:** que cada interfaz encadene retriever, prompt y LLM por
  su cuenta. Funcionaría, pero cada una repetiría esos pasos y cualquier cambio del
  flujo habría que replicarlo en todas.
- **Sobre el alcance:** la fachada no guarda el historial: lo recibe como parámetro
  (`historial`, una lista de mensajes `{"role", "content"}`). Guardarlo por
  `session_id` es trabajo de `ServicioChat` (etapa 6).

### Repository: historial (extra)

- **Qué es:** `Historial` (`src/memory/historial.py`) define cómo se guardan y se leen los
  mensajes de una conversación (`agregar`, `ultimos`) y recorre todas (`todos`, lo que usa
  el análisis de la etapa 8) sin decir dónde; `HistorialSQLite` es la implementación local.
  `ServicioChat` y el cálculo del análisis solo conocen la interfaz.
- **Por qué aquí:** la persistencia es un detalle que puede cambiar (otra base, un
  servicio externo). Con un repositorio ese cambio no toca la lógica de la conversación,
  y las pruebas pueden usar una base temporal.
- **Sobre el alcance:** hoy solo existe la implementación SQLite, que crea la misma
  fábrica de proveedores (`crear_historial`).

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
| Ollama + `qwen3:4b-instruct` (cliente `ollama`) | LLM | Modelo de código abierto que corre en local, sin costo ni API externa. El hardware de desarrollo es una GTX 1060 de 6 GB, que limita a modelos pequeños. Se usa la variante *instruct*, mucho más rápida que la que razona |
| `sqlite3` (stdlib) | Historial de conversaciones | Viene con Python, no necesita servidor y un solo archivo basta |
| FastAPI + uvicorn | API web | Validación de entrada y documentación automática con poco código |
| Docker + Docker Compose | Despliegue | Un solo comando levanta la aplicación, la base vectorial y el modelo de lenguaje. Chroma y Ollama usan sus imágenes oficiales y la aplicación se construye con su `Dockerfile` |
| HTML + JavaScript sin librerías | Página de chat | Una sola página que no necesita internet ni compilación y se sirve igual dentro de Docker |

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
- **La base vectorial no se versiona** (`data/chroma/`, decenas de MB). Con Docker la crea
  el servicio `indexador` en el primer arranque; sin Docker hay que ejecutar el indexador
  (unos minutos y descarga del modelo).
- **Chroma en Docker exige que cliente y servidor tengan la misma versión.** La imagen está
  fijada a `chromadb==1.5.9` en `docker-compose.yml`; al actualizar `requirements.txt` hay
  que cambiarla también.
- **Los embeddings se calculan en CPU.** Basta para una indexación que se hace una
  vez, pero la versión de PyTorch instalada no usa la GPU.
- **La reescritura de las preguntas de seguimiento depende del modelo.** A veces añade
  o pierde un detalle; por eso la interfaz muestra con qué pregunta se buscó. Los
  seguimientos muy cortos (*"¿Y el factoring?"*) a veces vuelven sin cambios y la búsqueda
  falla aunque el sitio tenga la página.
- **El modelo puede quedarse con un fragmento poco adecuado** cuando el correcto no
  queda entre los primeros resultados de la búsqueda.
- **Las fuentes que se muestran son las recuperadas**, aunque la pregunta no tenga
  relación con el sitio (por ejemplo, un saludo).
- **Una respuesta que abarca varios chunks depende de que todos entren** entre los
  fragmentos recuperados; una lista muy larga podría llegar incompleta.
- **El terminal responde una pregunta por ejecución** y vuelve a cargar el modelo de
  embeddings cada vez; para conversar se usa la interfaz web.
- **La respuesta aparece completa al terminar**, sin mostrarse mientras se genera; las
  largas tardan varios segundos.
- **Las peticiones se atienden de una en una.** Con varios usuarios a la vez, cada uno
  espera su turno (hay un solo modelo y una sola GPU).
- **Sin autenticación.** El ID de conversación es el único control: quien lo conozca puede
  leer esa conversación. Basta para una demo local, no para exponerla en internet.
- **Las conversaciones no se borran** ni tienen un tiempo de retención.
- **Ollama debe estar en ejecución** (con Docker lo levanta Compose). Sin GPU el modelo
  corre en CPU, bastante más lento. Con Docker la GPU se activa con `docker-compose.gpu.yml`
  y exige una NVIDIA.
- **La primera ejecución con Docker es lenta y pesada:** descarga varias imágenes y dos
  modelos y después indexa el sitio en CPU. Los arranques siguientes reutilizan los
  volúmenes y son mucho más rápidos.
- **El scraper y la limpieza no corren dentro de Docker.** El repositorio trae los datos ya
  limpios (`data/clean/`), que es lo que usa el indexador.
- **Pruebas automáticas solo para el historial, las métricas y el chat.** El resto del
  sistema se comprobó a mano.
- **Las métricas del historial describen el uso, no el impacto ni la calidad.** El
  enunciado pide "métricas y valores de impacto" y se entendió como el uso del asistente:
  cuántas conversaciones hay, de qué tamaño y cuánto duran. No se estima el tiempo ahorrado
  ni se mide si las respuestas fueron correctas.

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
- Mostrar la respuesta mientras se genera - *streaming*.
- Poder borrar conversaciones, fijar un tiempo de retención y listar las anteriores.
- Traer, junto a cada resultado, los chunks vecinos de su misma página, para que una
  lista o un procedimiento partido no llegue incompleto.
- Evaluación formal de la recuperación y de los modelos con un conjunto de preguntas y
  respuestas esperadas, para comparar también otros modelos pequeños (por ejemplo,
  Granite, Ministral o Qwen3.5) y otros embeddings.
- Mostrar las fuentes solo cuando la respuesta las use.
- Embeddings en GPU (instalando la build de PyTorch con CUDA) si el volumen crece.