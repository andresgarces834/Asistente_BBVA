"""Descarga el HTML renderizado de las páginas públicas de BBVA Colombia.

Las URLs se obtienen desde el sitemap.xml. Cada página se guarda como
un archivo HTML independiente y se genera un manifest.jsonl que relaciona
cada archivo con su URL original.

El scraper puede reanudarse: las URLs cuyo archivo ya existe se omiten.
No se realiza limpieza ni transformación del HTML.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree

from playwright.sync_api import sync_playwright

BASE_URL = "https://www.bbva.com.co"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
MANIFEST_PATH = RAW_DIR / "manifest.jsonl"

EXCLUDED_PATTERNS = (
    ".content.html",
    "/personas/cards",
)

RATE_LIMIT_SECONDS = 1
TIMEOUT_MS = 45_000

########################################################################
####################  EXTRACCION URLs SIN DUPLICAR  ####################
########################################################################

def filename_for_url(url: str) -> str:
    """Genera un nombre determinista para una URL"""

    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".html"

def parse_sitemap(xml: str) -> list[str]:
    """Extrae las URLs del sitemap"""

    root = ElementTree.fromstring(xml)

    urls = [
        loc.text.strip()
        for loc in root.findall(".//{*}loc")
        if loc.text
    ]
    if not urls:
        raise ValueError("El sitemap no contiene URLs.")

    return urls

def save_html(url: str, html: str) -> str:
    """Guarda el HTML y devuelve el nombre del archivo"""

    filename = filename_for_url(url)
    destination = RAW_DIR / filename
    temporary = RAW_DIR / f"{filename}.tmp"
    temporary.write_text(html, encoding="utf-8")
    temporary.replace(destination)

    return filename

########################################################################
###########################  MAIN - SCRAPER  ###########################
########################################################################

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximo de paginas a descargar.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Ejecutar Chrome sin mostrar la ventana.",
    )
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=args.headless,
        )
        context = browser.new_context(locale="es-CO")
        page = context.new_page()

        try:
            # Inicializamos el sitio antes de solicitar el sitemap para
            # conservar el mismo contexto de navegador.
            page.goto(
                BASE_URL,
                wait_until="domcontentloaded",
                timeout=TIMEOUT_MS,
            )

            response = context.request.get(SITEMAP_URL)

            if not response.ok:
                raise RuntimeError(
                    f"Sitemap: HTTP {response.status}"
                )

            urls = parse_sitemap(response.text())

            # Solo procesamos URLs del dominio objetivo y aplicamos
            # las exclusiones definidas para este dataset.
            domain = urlparse(BASE_URL).netloc
            urls = [
                url
                for url in urls
                if urlparse(url).netloc == domain
                and not any(
                    pattern in url
                    for pattern in EXCLUDED_PATTERNS
                )
            ]

            # Eliminamos duplicados manteniendo el orden del sitemap.
            urls = list(dict.fromkeys(urls))

            # Reanudación: si el HTML ya existe, no volvemos a descargarlo.
            urls = [
                url
                for url in urls
                if not (RAW_DIR / filename_for_url(url)).exists()
            ]

            if args.limit:
                urls = urls[:args.limit]

            print(f"URLs por descargar: {len(urls)}")

            with MANIFEST_PATH.open("a", encoding="utf-8") as manifest:
                for index, url in enumerate(urls, 1):
                    if page.is_closed():
                        print("El navegador se cerró. Deteniendo scraper.")
                        break

                    try:
                        response = page.goto(
                            url,
                            wait_until="domcontentloaded",
                            timeout=TIMEOUT_MS,
                        )

                        if response is None or not response.ok:
                            status = response.status if response else "sin respuesta"
                            raise RuntimeError(f"HTTP {status}")

                        # Guardamos el HTML renderizado sin limpiarlo
                        # ni transformarlo.
                        html = page.content()

                        filename = save_html(url, html)

                        manifest.write(
                            json.dumps(
                                {
                                    "url": url,
                                    "archivo": filename,
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                        manifest.flush()

                        print(
                            f"[{index}/{len(urls)}] OK {url}"
                        )

                    except Exception as exc:
                        print(
                            f"[{index}/{len(urls)}] "
                            f"ERROR {url}: {exc}"
                        )

                    time.sleep(RATE_LIMIT_SECONDS)

        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()