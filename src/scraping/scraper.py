"""Descarga el HTML renderizado de las páginas públicas de BBVA Colombia.

Las URLs se obtienen desde el sitemap.xml. Cada página se guarda como
un archivo HTML independiente y se genera un manifest.jsonl que relaciona
cada archivo con su URL original.

Varias pestañas descargan en paralelo (--workers) compartiendo una cola.

El scraper puede reanudarse: las URLs cuyo archivo ya existe se omiten.
No se realiza limpieza ni transformación del HTML.
"""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree

from playwright.async_api import async_playwright

BASE_URL = "https://www.bbva.com.co"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
MANIFEST_PATH = RAW_DIR / "manifest.jsonl"

EXCLUDED_PATTERNS = (
    ".content.html",
    "/personas/cards",
)

WORKERS = 10
RATE_LIMIT_SECONDS = 1  # pausa de cada worker entre páginas
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
##########################  WORKER - SCRAPER  ##########################
########################################################################

async def worker(queue: asyncio.Queue, context, manifest, total: int, counter: list[int]) -> None:
    """Toma URLs de la cola y las descarga en su propia pestaña"""

    page = await context.new_page()

    while True:
        try:
            url = queue.get_nowait()
        except asyncio.QueueEmpty:
            break

        if page.is_closed():
            print("El navegador se cerró. Deteniendo worker.")
            break

        try:
            response = await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=TIMEOUT_MS,
            )

            if response is None or not response.ok:
                status = response.status if response else "sin respuesta"
                raise RuntimeError(f"HTTP {status}")

            # Guardamos el HTML renderizado sin limpiarlo
            # ni transformarlo.
            html = await page.content()

            filename = save_html(url, html)

            # No hay await entre escribir y hacer flush, así que las
            # líneas de distintos workers nunca se mezclan.
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

            counter[0] += 1
            print(f"[{counter[0]}/{total}] OK {url}")

        except Exception as exc:
            counter[0] += 1
            print(f"[{counter[0]}/{total}] ERROR {url}: {exc}")

        await asyncio.sleep(RATE_LIMIT_SECONDS)

    await page.close()

########################################################################
###########################  MAIN - SCRAPER  ###########################
########################################################################

async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximo de paginas a descargar.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=WORKERS,
        help="Pestañas descargando en paralelo.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Ejecutar Chrome sin mostrar la ventana.",
    )
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome",
            headless=args.headless,
        )
        context = await browser.new_context(locale="es-CO")
        page = await context.new_page()

        try:
            # Inicializamos el sitio antes de solicitar el sitemap para
            # conservar el mismo contexto de navegador.
            await page.goto(
                BASE_URL,
                wait_until="domcontentloaded",
                timeout=TIMEOUT_MS,
            )

            response = await context.request.get(SITEMAP_URL)

            if not response.ok:
                raise RuntimeError(
                    f"Sitemap: HTTP {response.status}"
                )

            urls = parse_sitemap(await response.text())

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

            print(f"URLs por descargar: {len(urls)} ({args.workers} workers)")

            queue = asyncio.Queue()
            for url in urls:
                queue.put_nowait(url)

            await page.close()

            counter = [0]
            with MANIFEST_PATH.open("a", encoding="utf-8") as manifest:
                await asyncio.gather(*(
                    worker(queue, context, manifest, len(urls), counter)
                    for _ in range(args.workers)
                ))

        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
