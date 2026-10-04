"""Interfaces de los proveedores.

El resto del sistema solo conoce estas clases abstractas, nunca Chroma 
ni sentence-transformers directamente, así se puede cambiar un
proveedor sin tocar la lógica de negocio.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

@dataclass
class Resultado:
    """Un fragmento recuperado de la base vectorial"""

    texto: str
    metadatos: dict = field(default_factory=dict)
    score: float = 0.0  # similitud: mayor = más relevante

class Embeddings(ABC):
    @abstractmethod
    def embed_documentos(self, textos: list[str]) -> list[list[float]]:
        """Vectores de los textos que se van a indexar"""

    @abstractmethod
    def embed_consulta(self, texto: str) -> list[float]:
        """Vector de una pregunta del usuario"""

class VectorStore(ABC):
    @abstractmethod
    def agregar(self, ids: list[str], textos: list[str],
                embeddings: list[list[float]], metadatos: list[dict]) -> None: ...

    @abstractmethod
    def buscar(self, embedding: list[float], k: int,
               filtro: dict | None = None) -> list[Resultado]: ...

    @abstractmethod
    def existentes(self, ids: list[str]) -> set[str]:
        """De estos ids, cuáles ya están indexados"""

    @abstractmethod
    def contar(self) -> int: ...

    @abstractmethod
    def reiniciar(self) -> None:
        """Borra todo lo indexado"""

class LLM(ABC):
    @abstractmethod
    def generar(self, mensajes: list[dict]) -> str:
        """Respuesta del modelo. `mensajes`: [{'role': 'system'|'user'|'assistant', 'content': str}]"""
