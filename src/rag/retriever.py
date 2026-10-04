"""Recuperación: dada una pregunta, devuelve los fragmentos más parecidos."""

from src.providers.base import Embeddings, Resultado, VectorStore

class Retriever:
    def __init__(self, embeddings: Embeddings, store: VectorStore, top_k: int):
        self._embeddings = embeddings
        self._store = store
        self._top_k = top_k

    def recuperar(self, pregunta: str, filtro: dict | None = None) -> list[Resultado]:
        """`filtro` restringe por metadatos, p. ej. {"seccion": "empresas"}"""

        vector = self._embeddings.embed_consulta(pregunta)
        return self._store.buscar(vector, self._top_k, filtro)

    def contar(self) -> int:
        """Cuántos fragmentos hay indexados"""

        return self._store.contar()
