# Asistente BBVA — Sistema RAG con Web Scraping

Asistente conversacional que responde preguntas sobre el contenido del sitio
público de BBVA Colombia (<https://www.bbva.com.co/>) usando RAG. Prueba técnica de Machine Learning Engineer.

> **Estado: trabajo en progreso.** Este README se actualiza junto con el código.

## Estado del proyecto

| Etapa | Estado |
|---|---|
| 1. Scraping: descarga del HTML crudo | Hecho |
| 2. Limpieza y normalización del HTML | Siguiente |
| 3. Chunking, vectorización e indexación | Pendiente |
| 4. Interfaz conversacional | Pendiente |
| 5. Historial de conversación por ID | Pendiente |
| 6. Análisis del historial (métricas) | Pendiente |
| 7. Dockerización | Pendiente |

## Flujo de datos

```
sitemap.xml ---> [1. SCRAPER] ---> data/raw/*.html + manifest.jsonl

[2. LIMPIEZA]  ──► data/clean/   (siguiente)

```

Las etapas están separadas a propósito: el scraper solo descarga y guarda HTML
sin transformarlo. Toda la limpieza ocurre después, a partir de los datos crudos. 
Así se puede corregir o cambiar la limpieza sin volver a scrapear el sitio.

## Estructura del repositorio - pensada inicialmente

```
Asistente_BBVA/
├── data/
│   └── raw/                   # HTML crudo + manifest.jsonl
├── src/
│   ├── scraping/
│   │   └── scraper.py         # descarga paralela del HTML crudo      (done)
│   ├── ingestion/             # limpieza, normalización, chunking     (pendiente)
│   ├── providers/             # embeddings, vector store, LLM         (pendiente)
│   ├── rag/                   # recuperación y generación             (pendiente)
│   ├── memory/                # historial de conversaciones           (pendiente)
│   ├── analytics/             # métricas sobre el historial           (pendiente)
│   └── ui/                    # interfaz conversacional               (pendiente)
└── scripts/                   # - validar si son necesario            (pendiente)
```

## Requisitos previos

Para la etapa implementada (scraping):

- Python 3.13.5.
- **Google Chrome instalado** en el equipo. El scraper lo lanza con
  `channel="chrome"`.
- Conexión a internet.

> Todavía no hay `requirements.txt` ni Docker. Se agregarán al cerrar las
> siguientes etapas. Las variables de entorno (`.env`) tampoco son necesarias aún.

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
pip install playwright
```

### 3. Ejecutar el scraper

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

### 4. Cómo usar la interfaz conversacional

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

## Etapa 2 — Limpieza (siguiente)

Entrada: `data/raw/*.html` + `manifest.jsonl`. Salida prevista: `data/clean/`.

Alcance previsto:

- Extraer título, descripción, encabezados y texto del contenido principal
  (`<main>`), descartando scripts, estilos, navegación, pie de página y cookies.
- Conservar los encabezados como *markdown* para poder hacer chunking por secciones.
- Metadatos derivados de la URL (sección, categoría) para filtrar en la
  recuperación.
- Normalizar caracteres Unicode problemáticos.

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

El stack de las demás etapas (embeddings, base vectorial, LLM, interfaz) está pendiente 

## Limitaciones conocidas y decisiones de diseño

- **El scraping corre fuera de Docker.** El WAF de BBVA bloquea Chrome headless,
  por lo que el scraper abre una ventana real, algo que no funciona dentro de un
  contenedor. 
- **No se espera a que la red quede inactiva** antes de capturar el HTML. En una
  prueba de 10 páginas el contenido llegó completo, pero no se garantiza para las
  1.239. Si la limpieza detecta páginas vacías, habrá que volver a añadir esa
  espera.
- **Una página bloqueada por el WAF con HTTP 200 se guardaría como válida.** Hoy
  solo se valida el código de estado.
- **Posible inconsistencia si el proceso muere** justo entre guardar el HTML y
  escribir su línea en el manifest: la URL se daría por descargada sin figurar en
  él.
- **Los datos crudos pesan ~465 MB.**
- **Es una foto del sitio en un momento dado.** No hay actualización incremental.
- **Sin pruebas automáticas.**

## Futuras mejoras

- Guardar `lastmod`, fecha de descarga y código HTTP en el manifest.
- Detectar páginas de bloqueo del WAF.
- Actualización incremental usando `lastmod`.
- Registrar las URLs fallidas en un archivo para poder auditarlas.
- Pruebas unitarias de limpieza y parseo del sitemap.
