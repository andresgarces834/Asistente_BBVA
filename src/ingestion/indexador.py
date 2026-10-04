"""Vectoriza los chunks y los guarda en la base vectorial.

Lee data/clean/chunks.jsonl, calcula el embedding de cada chunk y lo indexa en
Chroma junto con sus metadatos. Es reanudable: los chunks que ya están
indexados (mismo id) se omiten.

Uso (desde la raíz del repo):
    python -m src.ingestion.indexador
    python -m src.ingestion.indexador --limit 200     # prueba rápida
    python -m src.ingestion.indexador --reiniciar     # borra y reindexa todo
"""

import argparse
import json
import time
from pathlib import Path

from src.config import obtener_config
from src.providers.factory import obtener_fabrica

RAIZ = Path(__file__).resolve().parents[2]
CHUNKS_PATH = RAIZ / "data" / "clean" / "chunks.jsonl"

LOTE = 128  # chunks por escritura a la base

# Metadatos que se guardan con cada chunk, para poder filtrar al recuperar.
CAMPOS_METADATOS = ("url", "titulo", "seccion", "categoria", "subcategoria", "orden", "repeticiones")

def texto_a_vectorizar(chunk: dict) -> str:
    """El título de la página se antepone: da contexto a chunks de mitad de página"""

    return f"{chunk['titulo']}\n{chunk['texto']}"

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="máximo de chunks a indexar")
    ap.add_argument("--reiniciar", action="store_true", help="borra lo indexado y empieza de cero")
    args = ap.parse_args()

    fabrica = obtener_fabrica(obtener_config())
    embeddings = fabrica.crear_embeddings()
    store = fabrica.crear_vector_store()

    if args.reiniciar:
        store.reiniciar()

    with CHUNKS_PATH.open(encoding="utf-8") as f:
        chunks = [json.loads(linea) for linea in f if linea.strip()]
    if args.limit:
        chunks = chunks[: args.limit]

    ya_indexados = store.existentes([c["id"] for c in chunks])
    pendientes = [c for c in chunks if c["id"] not in ya_indexados]
    print(f"{len(chunks)} chunks | {len(ya_indexados)} ya indexados | {len(pendientes)} por indexar")

    inicio = time.time()
    for i in range(0, len(pendientes), LOTE):
        lote = pendientes[i:i + LOTE]
        store.agregar(
            ids=[c["id"] for c in lote],
            textos=[c["texto"] for c in lote],
            embeddings=embeddings.embed_documentos([texto_a_vectorizar(c) for c in lote]),
            metadatos=[{k: c[k] for k in CAMPOS_METADATOS} for c in lote],
        )

        hechos = i + len(lote)
        transcurrido = time.time() - inicio
        restante = transcurrido / hechos * (len(pendientes) - hechos)
        print(f"[{hechos}/{len(pendientes)}] {transcurrido:.0f}s transcurridos, ~{restante:.0f}s restantes")

    print(f"Listo. Chunks en la base: {store.contar()}")

if __name__ == "__main__":
    main()
