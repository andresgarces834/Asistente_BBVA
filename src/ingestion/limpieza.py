"""Convierte el HTML crudo "data/raw/" en texto limpio "data/clean/".

Lee data/raw/manifest.jsonl y, por cada página:
    1. Extrae título, descripción y el contenido de <main>.
    2. Quita el ruido de interfaz (migas de pan, botones de compartir, etc.).
    3. Conserva los títulos como markdown (#, ##) para poder hacer chunking por secciones, y las listas como "- ".
    4. Reconstruye las pestañas: la etiqueta de cada una va delante de su contenido.
    5. Normaliza caracteres unicode problematicos.

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
from bs4.element import NavigableString

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
    texto = texto.replace("\u2028", "\n").replace("\u2029", "\n\n")

    # Invisibles: espacio de ancho cero y guión suave.
    texto = re.sub(r"[\u200b\u200c\u200d\u2060\ufeff\u00ad]", "", texto)
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

def comparable(texto: str) -> str:
    """Texto sin diferencias de espacios ni mayúsculas, para compararlo"""

    return re.sub(r"\s+", " ", texto).strip().lower()

def etiqueta_en_panel(etiqueta: str, panel) -> bool:
    """¿El panel ya muestra la etiqueta como su propio título?

    Cuenta si el panel empieza con ella o si hay un texto que es exactamente la
    etiqueta. No basta con que aparezca dentro de una frase: "Leasing" está en
    "Soporte para el pago del Leasing" y eso no es un título.
    """

    buscada = comparable(etiqueta)
    if comparable(panel.get_text(" ", strip=True)).startswith(buscada):
        return True
    return panel.find(string=lambda s: comparable(s) == buscada) is not None

def reconstruir_pestanas(main) -> None:
    """Pone la etiqueta de cada pestaña delante del contenido de su panel.

    El HTML enlaza cada pestaña (role=tab) con su panel (role=tabpanel) mediante
    aria-controls, pero en texto plano todas las etiquetas quedaban juntas y lejos
    de su contenido: no se sabía qué viñetas eran de "Comercio exterior" o de
    "Leasing". Solo se actúa cuando la etiqueta NO aparece ya dentro de su panel
    (las pestañas de preguntas frecuentes repiten su título y no pierden nada).

    La etiqueta se escribe como línea en negrita y no como título: así el grupo de
    pestañas sigue siendo una sola sección bajo su título común, y la pregunta
    general ("¿qué puedo hacer en mi línea?") sigue encontrando todo el contenido.
    """

    por_lista = {}
    for pestana in main.select("[role=tab][aria-controls]"):
        lista = pestana.find_parent(attrs={"role": "tablist"}) or pestana.parent
        por_lista.setdefault(id(lista), []).append(pestana)

    for pestanas in por_lista.values():
        sin_etiqueta = []
        for pestana in pestanas:
            panel = main.find(id=pestana["aria-controls"])
            etiqueta = pestana.get_text(" ", strip=True)
            if panel is None or not etiqueta:
                continue
            if not etiqueta_en_panel(etiqueta, panel):
                sin_etiqueta.append((panel, etiqueta))

        for panel, etiqueta in sin_etiqueta:
            panel.insert(0, NavigableString(f"\n\n**{etiqueta}**\n\n"))

        # Si todas las etiquetas ya viven en su panel, la lista de pestañas sobra.
        if sin_etiqueta and len(sin_etiqueta) == len(pestanas):
            for pestana in pestanas:
                pestana.decompose()

def extraer(html: str) -> dict | None:
    """Devuelve título, descripción, encabezados y texto, o None si no hay <main>"""

    soup = BeautifulSoup(html, "lxml")

    main = soup.find("main")
    if main is None:
        return None

    titulo = soup.title.get_text(strip=True) if soup.title else ""
    meta = soup.find("meta", attrs={"name": "description"})
    descripcion = str(meta.get("content") or "").strip() if meta else ""

    for tag in main.select(ETIQUETAS_RUIDO):
        tag.decompose()
    for tag in main.select(CLASES_RUIDO):
        tag.decompose()

    reconstruir_pestanas(main)

    # Títulos como markdown (#, ##, etc) y listas como "- ".
    for h in main.find_all(re.compile(r"^h[1-6]$")):
        if h.find_parent("li"):
            # El título de un elemento de lista (tarjetas, ilustraciones...) es el
            # texto de su viñeta, no una sección: con "##" quedaba "- ## Título".
            h.replace_with(h.get_text(" ", strip=True))
            continue
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
