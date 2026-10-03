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
| 4. Vectorización e indexación | Siguiente |
| 5. Interfaz conversacional | Pendiente |
| 6. Historial de conversación por ID | Pendiente |
| 7. Análisis del historial (métricas) | Pendiente |
| 8. Dockerización | Pendiente |

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
                          [4. EMBEDDINGS + BASE VECTORIAL]   (siguiente)
```

Las etapas están separadas a propósito: el scraper solo descarga y guarda HTML
sin transformarlo. Toda la limpieza ocurre después, a partir de los datos crudos. 
Así se puede corregir o cambiar la limpieza sin volver a scrapear el sitio.

## Estructura del repositorio - pensada inicialmente

```
Asistente_BBVA/
├── data/
│   ├── raw/                   # HTML crudo + manifest.jsonl (NO se versiona)
│   └── clean/                 # paginas, descartadas y chunks (.jsonl, sí se versiona)
├── src/
│   ├── scraping/
│   │   └── scraper.py         # descarga paralela del HTML crudo      (done)
│   ├── ingestion/
│   │   └── limpieza.py        # HTML crudo -> texto limpio            (done)
│   │   └── chunking.py        # páginas -> chunks (Strategy)          (done)
│   ├── providers/             # embeddings, vector store, LLM         (pendiente)
│   ├── rag/                   # recuperación y generación             (pendiente)
│   ├── memory/                # historial de conversaciones           (pendiente)
│   ├── analytics/             # métricas sobre el historial           (pendiente)
│   └── ui/                    # interfaz conversacional               (pendiente)
└── scripts/                   # - validar si son necesario            (pendiente)
```

## Requisitos previos

Para las etapas implementadas (scraping, limpieza y chunking):

- Python 3.13.5.
- **Google Chrome instalado**, pero solo si se va a ejecutar el scraper (paso 3,
  opcional). Se lanza con `channel="chrome"`.
- Conexión a internet para el scraper.

Todavía no hay Docker. Las variables de entorno (`.env`) tampoco son necesarias
aún.

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

### 6. Cómo usar la interfaz conversacional

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
   para poder hacer chunking por secciones, y las listas a `- `.
4. **Normaliza Unicode:** `U+2028`/`U+2029` pasan a saltos de línea; se eliminan
   los caracteres invisibles; `NBSP` pasa a espacio normal, se ordenan los
   espacios y saltos de línea.
5. **Metadatos desde la URL:** `seccion`, `categoria` y `subcategoria`, para
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
| Limpias (`paginas.jsonl`) | 1.200 |
| Descartadas (`descartadas.jsonl`) | 40 |

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
  salto de párrafo o de línea y no a mitad de palabra.
- **`fija` (línea base):** ventana de 1.000 caracteres sobre todo el texto, sin
  mirar los encabezados.

### Resultado (1.200 páginas)

| | `headings` | `fija` |
|---|---|---|
| Chunks finales (tras deduplicar) | **7.659** | 6.229 |
| Tamaño mediano | 571 caracteres | 936 |
| Chunks que empiezan con un encabezado | 72 % | 19 % |

Se eligió `headings` porque sus chunks corresponden a secciones reales de la
página (con su título), lo que da fragmentos más coherentes al recuperar. En la
práctica genera 10.149 chunks: descarta 595 de menos de 80 caracteres y 1.895
repetidos.

### Deduplicación

Cada chunk se identifica por una huella del texto (ignorando mayúsculas y
espacios). Si el mismo texto aparece en otra página, se conserva solo la primera
copia y se suma `repeticiones`. El caso más repetido, un bloque de FAQs de
tarjetas, aparecía 238 veces.

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

## Patrones de diseño

| Patrón | Tipo | Dónde | Estado |
|---|---|---|---|
| **Strategy** | Comportamental | `src/ingestion/chunking.py` | Hecho |
| **Factory** | Creacional | Proveedores (embeddings, base vectorial, LLM) | Pendiente |

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

Decisiones ya tomadas, aún sin implementar:

| Tecnología | Uso | Justificación |
|---|---|---|
| `multilingual-e5-small` | Embeddings | Multilingüe (el contenido está en español), gratuito y pequeño. Admite 512 tokens, que caben los chunks de ~1.000 caracteres. Se ejecutará en CPU para dejar la VRAM al LLM |
| Ollama + modelo local | LLM | Modelos de código abierto que corren en local, sin costo. El hardware de desarrollo es una GTX 1060 de 6 GB, que limita a modelos pequeños (3B por defecto; 7B opcional) |

La base vectorial y la interfaz están pendientes de definir.

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
- **La limpieza descarta páginas con menos de 200 caracteres.** Entre ellas
  algunos artículos de blog muy cortos quedan fuera.
- **Las listas pueden contener títulos.** Algunos elementos `<li>` son en realidad
  títulos de bloque (`- PORTAFOLIO BÁSICO`) y se conservan como viñeta.
- **Es una foto del sitio en un momento dado.** No hay actualización incremental.
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
