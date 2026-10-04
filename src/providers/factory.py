"""Patrón Factory (Abstract Factory): crea la familia de proveedores que van juntos.

`FabricaProveedores` define qué se crea (embeddings, base vectorial, LLM e historial);
cada subclase define como y con que tecnología. Hoy solo existe la familia
`local`. Añadir otra es una subclase más y una línea
en FABRICAS, sin modificar el código que usa la fábrica.
"""

from abc import ABC, abstractmethod

from src.config import RAIZ, Config
from src.memory.historial import Historial, HistorialSQLite
from src.providers.base import LLM, Embeddings, VectorStore
from src.providers.local import ChromaVectorStore, E5Embeddings, OllamaLLM

class FabricaProveedores(ABC):
    def __init__(self, config: Config):
        self.config = config

    @abstractmethod
    def crear_embeddings(self) -> Embeddings: ...

    @abstractmethod
    def crear_vector_store(self) -> VectorStore: ...

    @abstractmethod
    def crear_llm(self) -> LLM: ...

    @abstractmethod
    def crear_historial(self) -> Historial: ...

class FabricaLocal(FabricaProveedores):
    def crear_embeddings(self) -> Embeddings:
        c = self.config
        return E5Embeddings(c.embedding_model, c.embedding_batch)

    def crear_vector_store(self) -> VectorStore:
        return ChromaVectorStore(self.config)

    def crear_llm(self) -> LLM:
        return OllamaLLM(self.config)

    def crear_historial(self) -> Historial:
        return HistorialSQLite(RAIZ / self.config.historial_path)

FABRICAS: dict[str, type[FabricaProveedores]] = {"local": FabricaLocal}

def obtener_fabrica(config: Config) -> FabricaProveedores:
    try:
        return FABRICAS[config.perfil](config)
    except KeyError:
        raise ValueError(
            f"PERFIL '{config.perfil}' no soportado. Opciones: {', '.join(FABRICAS)}"
        ) from None