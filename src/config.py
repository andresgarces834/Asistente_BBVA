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

    # LLM (Ollama). num_ctx: el contexto por defecto de Ollama es corto y recorta
    # el prompt en silencio; con 5 fragmentos más el historial hace falta más.
    ollama_host: str = "http://localhost:11434"
    llm_model: str = "qwen3:4b-instruct"
    llm_num_ctx: int = 4096
    llm_temperature: float = 0.2

    # Recuperación
    top_k: int = 5

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
        ollama_host=os.getenv("OLLAMA_HOST", d.ollama_host),
        llm_model=os.getenv("LLM_MODEL", d.llm_model),
        llm_num_ctx=int(os.getenv("LLM_NUM_CTX", d.llm_num_ctx)),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", d.llm_temperature)),
        top_k=int(os.getenv("TOP_K", d.top_k)),
    )
