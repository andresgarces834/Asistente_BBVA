"""Configuración centralizada: cada parámetro sale del .env o de su valor por defecto.

Se lee una sola vez y se comparte (`obtener_config` devuelve siempre el mismo
objeto). Los parámetros se irán añadiendo a medida que cada etapa los necesite.
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[1]

@dataclass(frozen=True)
class Config:
    # Qué familia de proveedores usar (ver providers/factory.py)
    perfil: str = "local"

    # Embeddings
    embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_batch: int = 32

    # Base vectorial (Chroma). Con CHROMA_HOST vacío corre embebida en
    # CHROMA_PATH; con host, se conecta al servidor (el de docker-compose).
    chroma_host: str = ""
    chroma_port: int = 8000
    chroma_path: str = "data/chroma"
    chroma_collection: str = "bbva"

@lru_cache(maxsize=1)
def obtener_config() -> Config:
    load_dotenv(RAIZ / ".env")
    d = Config()
    return Config(
        perfil=os.getenv("PERFIL", d.perfil),
        embedding_model=os.getenv("EMBEDDING_MODEL", d.embedding_model),
        embedding_batch=int(os.getenv("EMBEDDING_BATCH", d.embedding_batch)),
        chroma_host=os.getenv("CHROMA_HOST", d.chroma_host),
        chroma_port=int(os.getenv("CHROMA_PORT", d.chroma_port)),
        chroma_path=os.getenv("CHROMA_PATH", d.chroma_path),
        chroma_collection=os.getenv("CHROMA_COLLECTION", d.chroma_collection),
    )
