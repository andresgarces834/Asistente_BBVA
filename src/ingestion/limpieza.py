"""Convierte el HTML crudo "data/raw/" en texto limpio "data/clean/".

Lee data/raw/manifest.jsonl y, por cada página:
    1. Extrae título, descripción y el contenido de <main>.
    2. Quita el ruido de interfaz (migas de pan, botones de compartir, etc.).
    3. Conserva los títulos como markdown (#, ##) para poder hacer chunking por secciones, y las listas como "- ".
    4. Normaliza caracteres unicode problematicos.

Salida:
    data/clean/paginas.jsonl      una pagina limpia por línea
    data/clean/descartadas.jsonl  paginas sin contenido útil, con el motivo

Es determinista y no toca los crudos: se puede volver a ejecutar cuantas veces
haga falta (sobrescribe la salida).

Uso (desde la raíz del repo):
    python -m src.ingestion.limpieza
"""

import json
import re
import statistics
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup

RAIZ = Path(__file__).resolve().parents[2]
RAW_DIR = RAIZ / "data" / "raw"
MANIFEST_PATH = RAW_DIR / "manifest.jsonl"
CLEAN_DIR = RAIZ / "data" / "clean"
SALIDA_PATH = CLEAN_DIR / "paginas.jsonl"
DESCARTADAS_PATH = CLEAN_DIR / "descartadas.jsonl"

BASE_URL = "https://www.bbva.com.co"
SUFIJO_TITULO = re.compile(r"\s*\|\s*BBVA Colombia\s*$")

# Menos caracteres que esto = página sin contenido útil, se mueve a descartadas.jsonl.
MIN_CHARS = 200

# Elementos que no aportan texto.
ETIQUETAS_RUIDO = "script, style, noscript, svg, iframe, template"

# Componentes de interfaz detectados en el análisis de los crudos.
CLASES_RUIDO = (
    "[class*=breadcrumb], [class*=sharestickybuttons], "
    "[class*=slider-navigation], [class*=slider__nav], "
    "[class*=print__footer], [class*=cookie]"
)

# Líneas que son botones o etiquetas de interfaz y no contenido.
LINEAS_RUIDO = {
    "más información", "conoce más", "ver más", "anterior", "siguiente",
    "cerrar", "contactar", "ir a app bbva", "publicidad",
    "twitter", "linkedin", "facebook", "whatsapp",
}
PAGINACION = re.compile(r"\d+ (de|of) \d+", re.IGNORECASE)  # "1 de 1", "1 of 3"
FECHA = re.compile(r"\d{2}/\d{2}/\d{4}")

########################################################################
########################### NORMALIZACION  #############################
########################################################################

def normalizar(texto: str) -> str:
    """Normaliza Unicode y espacios, sin alterar el contenido"""

    texto = unicodedata.normalize("NFC", texto)

    # Separadores de línea/párrafo que algunos lectores tratan como saltos.
    texto = texto.replace(" ", "\n").replace(" ", "\n\n")

    # Invisibles: espacio de ancho cero y guión suave.
    texto = re.sub(r"[​‌‍⁠﻿­]", "", texto)
    texto = texto.replace("\xa0", " ")
    texto = re.sub(r"[ \t\r\f\v]+", " ", texto)

    return texto

def limpiar_lineas(texto: str) -> str:
    """Quita el ruido de interfaz línea por línea y ordena los saltos"""

    # Una viñeta queda en su propia línea; se une a su texto.
    texto = re.sub(r"^- *\n+", "- ", texto, flags=re.M)

    lineas = []
    despues_de_publicidad = False

    for linea in (l.strip() for l in texto.split("\n")):
        clave = linea.lower()

        # Las líneas en blanco no cuentan para detectar la secuencia.
        if linea:
            # "PUBLICIDAD" va seguida de la fecha del día, inyectada por el sitio.
            if despues_de_publicidad and FECHA.fullmatch(linea):
                despues_de_publicidad = False
                continue
            despues_de_publicidad = clave == "publicidad"

        if clave in LINEAS_RUIDO or PAGINACION.fullmatch(linea):
            continue

        lineas.append(linea)

    texto = "\n".join(lineas)
    texto = re.sub(r"^- +", "- ", texto, flags=re.M)  # sangría heredada del HTML
    texto = re.sub(r"\n{3,}", "\n\n", texto)

    return texto.strip()

########################################################################
###########################  EXTRACCION DE HTML  #######################
########################################################################

def clasificar(url: str) -> dict:
    """Sección y categoría de la URL, para poder filtrar al recuperar"""

    partes = [p for p in url.replace(BASE_URL, "").split("/") if p]
    partes = [p.removesuffix(".html") for p in partes]

    return {
        "seccion": partes[0] if partes else "home",
        "categoria": partes[1] if len(partes) > 1 else "",
        "subcategoria": partes[2] if len(partes) > 2 else "",
    }

def extraer(html: str) -> dict | None:
    """Devuelve título, descripción, encabezados y texto, o None si no hay <main>"""

    soup = BeautifulSoup(html, "lxml")

    main = soup.find("main")
    if main is None:
        return None

    titulo = soup.title.get_text(strip=True) if soup.title else ""
    meta = soup.find("meta", attrs={"name": "description"})
    descripcion = (meta.get("content") or "").strip() if meta else ""

    for tag in main.select(ETIQUETAS_RUIDO):
        tag.decompose()
    for tag in main.select(CLASES_RUIDO):
        tag.decompose()

    # Títulos como markdown (#, ##, etc) y listas como "- ".
    for h in main.find_all(re.compile(r"^h[1-6]$")):
        nivel = int(h.name[1])
        h.replace_with(f"\n\n{'#' * nivel} {h.get_text(' ', strip=True)}\n\n")
    for li in main.find_all("li"):
        li.insert_before("\n- ")

    texto = limpiar_lineas(normalizar(main.get_text(separator="\n")))
    headings = re.findall(r"^#{1,6} (.+)$", texto, flags=re.M)

    return {
        "titulo": SUFIJO_TITULO.sub("", normalizar(titulo)),
        "descripcion": normalizar(descripcion),
        "headings": headings,
        "texto": texto,
    }

########################################################################
################################  MAIN  ################################
########################################################################

def main() -> None:
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    with MANIFEST_PATH.open(encoding="utf-8") as f:
        manifest = [json.loads(linea) for linea in f if linea.strip()]

    largos = []
    descartadas = []

    with SALIDA_PATH.open("w", encoding="utf-8") as salida:
        for entrada in manifest:
            url = entrada["url"]
            html = (RAW_DIR / entrada["archivo"]).read_text(encoding="utf-8")
            contenido = extraer(html)

            if contenido is None:
                descartadas.append({"url": url, "motivo": "sin_main"})
                continue
            if len(contenido["texto"]) < MIN_CHARS:
                descartadas.append({
                    "url": url,
                    "motivo": "poco_texto",
                    "caracteres": len(contenido["texto"]),
                })
                continue

            registro = {
                "url": url,
                **clasificar(url),
                **contenido,
                "archivo_raw": entrada["archivo"],
            }
            salida.write(json.dumps(registro, ensure_ascii=False) + "\n")
            largos.append(len(contenido["texto"]))

    with DESCARTADAS_PATH.open("w", encoding="utf-8") as f:
        for d in descartadas:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    print(f"Páginas en el manifest: {len(manifest)}")
    print(f"Limpias:                {len(largos)}  -> {SALIDA_PATH.relative_to(RAIZ)}")
    print(f"Descartadas:            {len(descartadas)}  -> {DESCARTADAS_PATH.relative_to(RAIZ)}")

if __name__ == "__main__":
    main()
