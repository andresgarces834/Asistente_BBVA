"""Divide las páginas limpias en fragmentos (chunks) para indexarlos.

Lee data/clean/paginas.jsonl y escribe data/clean/chunks.jsonl, un chunk por
línea, con los metadatos de su página para poder filtrar al recuperar.

Patrón Strategy (comportamental): `Chunker` define QUÉ se hace (dividir una
página) y cada subclase define CÓMO. Se elige con --estrategia, así que se
pueden comparar sobre los mismos datos sin tocar el resto del pipeline.

    - headings (por defecto): respeta las secciones (# ...) de la página.
    - fija: ventana de tamaño fijo, sin mirar la estructura. Es la línea base.

Además elimina los chunks repetidos: bloques enteros aparecen en cientos de 
páginas y llenarían los resultados de copias.

Uso (desde la raíz del repo):
    python -m src.ingestion.chunking
    python -m src.ingestion.chunking --estrategia fija --size 800
"""

import argparse
import hashlib
import json
import re
import statistics
from abc import ABC, abstractmethod
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
ENTRADA_PATH = RAIZ / "data" / "clean" / "paginas.jsonl"
SALIDA_PATH = RAIZ / "data" / "clean" / "chunks.jsonl"

CHUNK_SIZE = 1000      # caracteres máximos por chunk
CHUNK_OVERLAP = 100    # solape entre trozos de una sección larga
MIN_CHARS = 300        # una sección más corta que esto se une a la siguiente
MIN_CHUNK = 80         # un chunk final más corto que esto no aporta nada: se descarta

########################################################################
#######################  CORTE DE TEXTO LARGO  #########################
########################################################################

def cortar(texto: str, size: int, overlap: int) -> list[str]:
    """Parte un texto en trozos de hasta `size` caracteres, con solape.

    Intenta cortar en un salto de párrafo, de línea o en un espacio, para no
    partir frases ni palabras por la mitad.
    """
    trozos = []
    inicio = 0
    n = len(texto)

    while inicio < n:
        fin = min(inicio + size, n)

        if fin < n:
            # Mejor punto de corte dentro de la segunda mitad de la ventana.
            for separador in ("\n\n", "\n", " "):
                corte = texto.rfind(separador, inicio + size // 2, fin)
                if corte != -1:
                    fin = corte + len(separador)
                    break

        trozo = texto[inicio:fin].strip()
        if trozo:
            trozos.append(trozo)

        if fin >= n:
            break

        inicio = fin - overlap
        # No empezar a mitad de palabra.
        if inicio > 0 and not texto[inicio - 1].isspace():
            espacio = texto.find(" ", inicio, inicio + 30)
            if espacio != -1:
                inicio = espacio + 1

    return trozos

########################################################################
#################  STRATEGY: ESTRATEGIAS DE CHUNKING  ##################
########################################################################

class Chunker(ABC):
    """Interfaz común: recibe una página y devuelve su lista de textos"""

    def __init__(self, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP,
                 min_chars: int = MIN_CHARS):
        self.size = size
        self.overlap = overlap
        self.min_chars = min_chars

    @abstractmethod
    def dividir(self, pagina: dict) -> list[str]: ...

class FixedSizeChunker(Chunker):
    """Ventana de tamaño fijo sobre todo el texto, ignorando la estructura"""

    def dividir(self, pagina: dict) -> list[str]:
        return cortar(pagina["texto"], self.size, self.overlap)

class HeadingChunker(Chunker):
    """Respeta las secciones de la página (encabezados markdown).

    - Una sección de tamaño normal es un chunk por sí sola.
    - Las secciones muy cortas (un encabezado casi solo) se unen a la siguiente.
    - Una sección que no cabe en `size` se parte con `cortar`.
    """

    def dividir(self, pagina: dict) -> list[str]:
        secciones = [s.strip() for s in re.split(r"(?m)^(?=#{1,6} )", pagina["texto"])]
        chunks = []
        buffer = ""

        for seccion in filter(None, secciones):
            # Lo acumulado ya tiene entidad propia: se cierra antes de seguir.
            if buffer and len(buffer) >= self.min_chars:
                chunks.append(buffer)
                buffer = ""

            if len(buffer) + len(seccion) + 2 <= self.size:
                buffer = f"{buffer}\n\n{seccion}" if buffer else seccion
                continue

            # No cabe: se cierra lo acumulado y se parte la sección grande.
            if buffer:
                chunks.append(buffer)
                buffer = ""
            if len(seccion) <= self.size:
                buffer = seccion
            else:
                *completos, resto = cortar(seccion, self.size, self.overlap)
                chunks.extend(completos)
                buffer = resto

        if buffer:
            chunks.append(buffer)

        return chunks

ESTRATEGIAS = {
    "headings": HeadingChunker,
    "fija": FixedSizeChunker,
}

########################################################################
###############################  MAIN  #################################
########################################################################

def clave(texto: str) -> str:
    """Huella del texto, ignorando mayúsculas y espacios, para detectar repetidos"""

    normal = re.sub(r"\s+", " ", texto).strip().lower()
    return hashlib.sha1(normal.encode("utf-8")).hexdigest()[:16]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--estrategia", choices=ESTRATEGIAS, default="headings")
    ap.add_argument("--size", type=int, default=CHUNK_SIZE)
    ap.add_argument("--overlap", type=int, default=CHUNK_OVERLAP)
    ap.add_argument("--min-chars", type=int, default=MIN_CHARS)
    ap.add_argument("--salida", type=Path, default=SALIDA_PATH)
    args = ap.parse_args()

    chunker = ESTRATEGIAS[args.estrategia](args.size, args.overlap, args.min_chars)

    with ENTRADA_PATH.open(encoding="utf-8") as f:
        paginas = [json.loads(linea) for linea in f if linea.strip()]

    unicos: dict[str, dict] = {}
    generados = descartados = 0

    for pagina in paginas:
        for orden, texto in enumerate(chunker.dividir(pagina)):
            generados += 1
            if len(texto) < MIN_CHUNK:
                descartados += 1
                continue

            id_ = clave(texto)
            if id_ in unicos:
                unicos[id_]["repeticiones"] += 1
                continue

            unicos[id_] = {
                "id": id_,
                "url": pagina["url"],
                "titulo": pagina["titulo"],
                "seccion": pagina["seccion"],
                "categoria": pagina["categoria"],
                "subcategoria": pagina["subcategoria"],
                "orden": orden,
                "texto": texto,
                "repeticiones": 0,  # veces que se encontró este mismo texto en otras páginas
            }

    args.salida.parent.mkdir(parents=True, exist_ok=True)
    with args.salida.open("w", encoding="utf-8") as f:
        for chunk in unicos.values():
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    largos = sorted(len(c["texto"]) for c in unicos.values())
    repetidos = generados - descartados - len(unicos)
    print(f"Estrategia:            {args.estrategia} (size {args.size}, overlap {args.overlap})")
    print(f"Páginas:               {len(paginas)}")
    print(f"Chunks generados:      {generados}")
    print(f"  descartados (<{MIN_CHUNK}):  {descartados}")
    print(f"  repetidos:           {repetidos}")
    print(f"Chunks finales:        {len(unicos)}  -> {args.salida.name}")
    print(f"Caracteres por chunk:  mediana {int(statistics.median(largos))}, "
          f"p90 {largos[int(len(largos) * 0.9)]}, máx {largos[-1]}")


if __name__ == "__main__":
    main()
