# Asistente BBVA — Sistema RAG con Web Scraping

Asistente conversacional que responde preguntas sobre el contenido del sitio
público de BBVA Colombia (<https://www.bbva.com.co/>) usando RAG. Prueba técnica de Machine Learning Engineer.

> **Estado: trabajo en progreso.** Este README se actualiza junto con el código.

## Estado del proyecto

| Etapa | Estado |
|---|---|
| 1. Scraping: descarga del HTML crudo | Hecho |
| 2. Limpieza y normalización del HTML | Hecho |
| 3. Chunking, vectorización e indexación | Siguiente |
| 4. Interfaz conversacional | Pendiente |
| 5. Historial de conversación por ID | Pendiente |
| 6. Análisis del historial (métricas) | Pendiente |
| 7. Dockerización | Pendiente |

## Flujo de datos

```
sitemap.xml ---> [1. SCRAPER] ---> data/raw/*.html + manifest.jsonl

[2. LIMPIEZA] ---> data/clean/paginas.jsonl
                   data/clean/descartadas.jsonl
```

Las etapas están separadas a propósito: el scraper solo descarga y guarda HTML
sin transformarlo. Toda la limpieza ocurre después, a partir de los datos crudos. 
Así se puede corregir o cambiar la limpieza sin volver a scrapear el sitio.

## Estructura del repositorio - pensada inicialmente

```
Asistente_BBVA/
├── data/                      # no se versiona 
│   ├── raw/                   # HTML crudo + manifest.jsonl
│   └── clean/                 # paginas.jsonl + descartadas.jsonl
├── src/
│   ├── scraping/
│   │   └── scraper.py         # descarga paralela del HTML crudo      (done)
│   ├── ingestion/
│   │   └── limpieza.py        # HTML crudo -> texto limpio            (done)
│   │                          # chunking                              (pendiente)
│   ├── providers/             # embeddings, vector store, LLM         (pendiente)
│   ├── rag/                   # recuperación y generación             (pendiente)
│   ├── memory/                # historial de conversaciones           (pendiente)
│   ├── analytics/             # métricas sobre el historial           (pendiente)
│   └── ui/                    # interfaz conversacional               (pendiente)
└── scripts/                   # - validar si son necesario            (pendiente)
```

## Requisitos previos

Para las etapas implementadas (scraping y limpieza):

- Python 3.13.5.
- **Google Chrome instalado** en el equipo. El scraper lo lanza con
  `channel="chrome"`.
- Conexión a internet.

variables de entorno (`.env`) tampoco son necesarias aún.

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

Los datos **no están en el repositorio**, sin embargo se va a subir la data limpia
porque pesa mucho menos

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



### 5. Cómo usar la interfaz conversacional

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

Antes de escribir reglas se analizaron los 1.240 HTML crudos. Dos mediciones
guiaron el diseño:

- **Estructura:** 1.233 páginas tienen un único `<main>` y 7 no tienen; la
  mediana de texto es ~4.000 caracteres. Sobre el contenido se detectaron
  separadores `U+2028` (21), espacios de ancho cero `U+200B` (178), espacios
  duros `NBSP` (385) y guiones suaves (16).
- **Ruido de interfaz:** se contó cuántas páginas repiten cada línea de texto.
  Las que aparecen solas en una línea en más del 15 % de las páginas son botones y
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
   los caracteres invisibles; `NBSP` pasa a espacio normal; se ordenan los
   espacios y saltos de línea. Tras la limpieza no queda ninguno de esos
   caracteres.
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

Una página se **descarta** si no tiene `<main>` (7) o si tras limpiar le quedan
menos de 200 caracteres (33). Revisadas una a una, casi todas son simuladores,
formularios, buscadores y organigramas (imágenes): no tienen texto que indexar.
Cada descarte queda registrado con su motivo, para poder auditarlo.

### Decisiones

- **NFC y no NFKC** al normalizar: NFKC convertiría `º` y `ª` en `o` y `a`
  (`N.º`, `1.ª`), algo incorrecto en español.
- **No se usa `<body>` como alternativa** cuando falta `<main>`: arrastraría
  cabecera, pie y cookies al índice; es preferible descartar la página.
- **`lxml` como parser.** Con `html.parser` el resultado fue idéntico en las 1.240
  páginas; `lxml` tolera mejor el HTML mal formado.
- **Reglas medidas, no supuestas:** la lista de ruido sale de la frecuencia real
  de las líneas, no de una intuición sobre el sitio.

## Patrones de diseño

*Pendiente.* El requisito es implementar al menos 3 patrones y documentar cuáles,
dónde y por qué. Se documentarán aquí a medida que se implementen, en las capas
donde existe una necesidad real.

El scraper **no aplica ningún patrón de forma deliberada**: tiene una sola fuente
y un solo navegador, así que no hay nada que elegir ni intercambiar, y forzar uno
añadiría complejidad sin beneficio.

## Stack tecnológico

Lo implementado hasta ahora:

| Tecnología | Uso | Justificación |
|---|---|---|
| Python | Lenguaje | Requisito de la prueba |
| Playwright (`playwright.async_api`) | Descarga del HTML renderizado | El sitio carga contenido con JavaScript y bloquea clientes HTTP simples; hace falta un navegador real. `asyncio` permite varias pestañas en paralelo |
| `xml.etree.ElementTree` (stdlib) | Parseo del sitemap | Sin dependencias extra |
| BeautifulSoup 4 + `lxml` | Extracción y limpieza del HTML | API sencilla para recorrer y modificar el árbol HTML; `lxml` es un parser rápido y tolerante con HTML roto |

El stack de las demás etapas (embeddings, base vectorial, LLM, interfaz) está pendiente 

## Limitaciones conocidas y decisiones de diseño

- **El scraping corre fuera de Docker.** El WAF de BBVA bloquea Chrome headless,
  por lo que el scraper abre una ventana real, algo que no funciona dentro de un
  contenedor. 
- **No se espera a que la red quede inactiva** antes de capturar el HTML. En una
  prueba de 10 páginas el contenido llegó completo, pero no se garantiza para las
  1.240. La limpieza no mostró cargas incompletas generalizadas (las páginas
  descartadas son casi todas simuladores o formularios), con una excepción: una
  descarga quedó mal guardada (8 KB, sin título) y hay que repetirla. Si se
  detectan más, habrá que volver a añadir esa espera.
- **Una página bloqueada por el WAF con HTTP 200 se guardaría como válida.** Hoy
  solo se valida el código de estado.
- **Posible inconsistencia si el proceso muere** justo entre guardar el HTML y
  escribir su línea en el manifest: la URL se daría por descargada sin figurar en
  él.
- **Los datos crudos pesan ~465 MB y no se versionan** en el repositorio
  (`data/` está en `.gitignore`), porque agregaban demasiado peso. La
  consecuencia es que, tras clonar, hay que ejecutar el scraper para generar los
  datos, y este necesita un Chrome con ventana y puede tardar.
- **Las páginas de la limpieza son una foto de la fecha de descarga**, y el sitio
  inyecta fechas dinámicas; solo se eliminó la que acompaña a `PUBLICIDAD`.
- **Contenido repetido entre páginas.** Bloques enteros (por ejemplo, FAQs de
  tarjetas) aparecen en cientos de páginas. La limpieza los conserva tal cual; la
  deduplicación se resolverá en el chunking.
- **La limpieza descarta páginas con menos de 200 caracteres.** Entre ellas
  algunos artículos de blog muy cortos (probablemente de video) quedan fuera.
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
- Reintentar la descarga que quedó incompleta (`plan-de-ahorro.html`).
- Detectar texto repetido entre páginas en la limpieza, en vez de esperar al
  chunking.
