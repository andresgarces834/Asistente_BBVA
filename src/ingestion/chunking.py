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
    partir frases ni palabras por la mitad. El solape también empieza, si puede,
    en un límite de párrafo: así un trozo no arranca a mitad de una viñeta.
    """
    overlap = min(overlap, size // 4)  # un solape grande impediría avanzar
    trozos = []
    inicio = 0
    n = len(texto)

    while inicio < n:
        fin = min(inicio + size, n)

        limite_de_grupo = False
        if fin < n:
            # Mejor punto de corte dentro de la segunda mitad de la ventana. El
            # preferido es justo antes de una etiqueta de grupo (**Leasing**, de las
            # pestañas): si el corte cae dentro de un grupo, las viñetas que pasan al
            # trozo siguiente se quedan sin la etiqueta que dice a qué pertenecen.
            for separador in ("\n\n**", "\n\n", "\n", " "):
                corte = texto.rfind(separador, inicio + size // 2, fin)
                if corte != -1:
                    limite_de_grupo = separador == "\n\n**"
                    fin = corte + (2 if limite_de_grupo else len(separador))
                    break

        trozo = texto[inicio:fin].strip()
        if trozo:
            trozos.append(trozo)

        if fin >= n:
            break

        if limite_de_grupo:
            inicio = fin  # el trozo siguiente arranca en la etiqueta: sin solape
            continue

        inicio = fin - overlap
        parrafo = texto.find("\n\n", inicio, fin)
        if parrafo != -1:
            inicio = parrafo + 2
        elif inicio > 0 and not texto[inicio - 1].isspace():
            # Sin límite de párrafo: al menos no empezar a mitad de palabra.
            espacio = texto.find(" ", inicio, inicio + 30)
            if espacio != -1:
                inicio = espacio + 1

    return trozos

def encabezado_de(seccion: str) -> str:
    """Primera línea de la sección si es un título markdown; si no, vacío"""

    primera = seccion.split("\n", 1)[0]
    return primera if re.match(r"#{1,6} ", primera) else ""

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
    - Una sección que no cabe en `size` se parte con `cortar`, y cada trozo
      repite el título de la sección. Sin él, un trozo de continuación no dice de
      qué trata y la búsqueda no lo encuentra (los chunks de una lista larga se
      quedaban sin el título que los relaciona con la pregunta).
    - Si una sección larga viene precedida de una introducción corta, se parten
      juntas, para que esa introducción no quede como un chunk casi vacío.
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

            union = self._unir(buffer, seccion)
            if len(union) <= self.size:
                buffer = union
                continue

            if len(seccion) <= self.size:
                # No cabe con lo acumulado, pero sí sola: se cierra lo acumulado.
                if buffer:
                    chunks.append(buffer)
                buffer = seccion
                continue

            # La sección es más larga que un chunk y hay que partirla de todos modos:
            # lo acumulado (corto) se une a ella en lugar de quedar aparte.
            *completos, resto = self._partir(union, encabezado_de(seccion))
            chunks.extend(completos)
            buffer = resto

        if buffer:
            chunks.append(buffer)

        return chunks

    @staticmethod
    def _unir(buffer: str, seccion: str) -> str:
        """Une lo acumulado con la sección, sin repetir un título idéntico.

        Hay páginas que repiten su título dos veces seguidas (un título suelto y,
        justo después, la sección con el mismo título).
        """

        if not buffer or buffer == encabezado_de(seccion):
            return seccion
        return f"{buffer}\n\n{seccion}"

    def _partir(self, texto: str, encabezado: str) -> list[str]:
        """Parte el texto y antepone `encabezado` a los trozos que no lo traen"""

        if not encabezado:
            return cortar(texto, self.size, self.overlap)

        encabezado = encabezado[: self.size // 3]  # un título larguísimo no debe comerse el chunk
        piezas = cortar(texto, self.size - len(encabezado) - 2, self.overlap)

        return [piezas[0]] + [
            pieza if pieza.startswith(encabezado) else f"{encabezado}\n\n{pieza}"
            for pieza in piezas[1:]
        ]

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
