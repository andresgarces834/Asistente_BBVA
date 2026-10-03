"""Proveedores locales / self-hosted: sentence-transformers (e5) y Chroma.

Los imports pesados son perezosos para que importar el módulo, o hacer pruebas
sin estas librerías, no las cargue.
"""

from src.config import RAIZ, Config
from src.providers.base import Embeddings, Resultado, VectorStore

# Lotes al consultar ids a Chroma (evita peticiones enormes).
LOTE_CONSULTA = 500

class E5Embeddings(Embeddings):
    """multilingual-e5: exige prefijos distintos para documentos y consultas.

    Sin "passage: " / "query: " la calidad de la recuperación baja bastante,
    así que se añaden aquí y el resto del sistema no tiene que saberlo.
    """

    def __init__(self, modelo: str, batch_size: int = 32):
        self._nombre = modelo
        self._batch_size = batch_size
        self._modelo = None

    def _cargar(self):
        if self._modelo is None:
            from sentence_transformers import SentenceTransformer
            # CPU a propósito: la VRAM de la GPU se reserva para el LLM.
            self._modelo = SentenceTransformer(self._nombre, device="cpu")
        return self._modelo

    def _vectorizar(self, textos: list[str]) -> list[list[float]]:
        return self._cargar().encode(
            textos,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

    def embed_documentos(self, textos: list[str]) -> list[list[float]]:
        return self._vectorizar([f"passage: {t}" for t in textos])

    def embed_consulta(self, texto: str) -> list[float]:
        return self._vectorizar([f"query: {texto}"])[0]

class ChromaVectorStore(VectorStore):
    def __init__(self, config: Config):
        import chromadb

        if config.chroma_host:
            self._cliente = chromadb.HttpClient(host=config.chroma_host, port=config.chroma_port)
        else:
            self._cliente = chromadb.PersistentClient(path=str(RAIZ / config.chroma_path))

        self._nombre = config.chroma_collection
        self._coleccion = self._crear_coleccion()

    def _crear_coleccion(self):
        # Distancia coseno; los embeddings ya vienen normalizados.
        return self._cliente.get_or_create_collection(
            self._nombre, metadata={"hnsw:space": "cosine"}
        )

    def agregar(self, ids, textos, embeddings, metadatos) -> None:
        self._coleccion.upsert(
            ids=ids, documents=textos, embeddings=embeddings, metadatas=metadatos
        )

    def buscar(self, embedding, k, filtro=None) -> list[Resultado]:
        r = self._coleccion.query(query_embeddings=[embedding], n_results=k, where=filtro)
        return [
            Resultado(texto=t, metadatos=m, score=1 - d)  # coseno: distancia -> similitud
            for t, m, d in zip(r["documents"][0], r["metadatas"][0], r["distances"][0])
        ]

    def existentes(self, ids: list[str]) -> set[str]:
        encontrados = set()
        for i in range(0, len(ids), LOTE_CONSULTA):
            lote = ids[i:i + LOTE_CONSULTA]
            encontrados.update(self._coleccion.get(ids=lote, include=[])["ids"])
        return encontrados

    def contar(self) -> int:
        return self._coleccion.count()

    def reiniciar(self) -> None:
        self._cliente.delete_collection(self._nombre)
        self._coleccion = self._crear_coleccion()
