"""Proveedores locales / self-hosted: sentence-transformers y Chroma.

Los imports pesados son perezosos para que importar el modulo, o hacer pruebas
sin estas librerías, no las cargue.
"""

import re
from src.config import RAIZ, Config
from src.providers.base import LLM, Embeddings, Resultado, VectorStore

# Lotes al consultar ids a Chroma.
LOTE_CONSULTA = 500

########################################################################
########################  CLASE EMBEDDINGS  ############################
########################################################################

class E5Embeddings(Embeddings):
    """multilingual-e5 - exige prefijos distintos para documentos y consultas.

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

########################################################################
###################  CLASE BASE DATOS VECTORIAL  #######################
########################################################################

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

    def agregar(self, ids: list[str], textos: list[str],
                embeddings: list[list[float]], metadatos: list[dict]) -> None:
        # Los tipos de Chroma tratan las listas como invariantes
        # no encaja en List[Sequence[float]]), así que se le pasan copias nuevas.
        self._coleccion.upsert(
            ids=ids,
            documents=textos,
            embeddings=[list(e) for e in embeddings],
            metadatas=[dict(m) for m in metadatos],
        )

    def buscar(self, embedding: list[float], k: int,
               filtro: dict | None = None) -> list[Resultado]:
        r = self._coleccion.query(query_embeddings=[embedding], n_results=k, where=filtro)
        # En los tipos de Chroma estos tres campos son opcionales (dependen de `include`).
        documentos = (r["documents"] or [[]])[0]
        metadatos = (r["metadatas"] or [[]])[0]
        distancias = (r["distances"] or [[]])[0]
        return [
            Resultado(texto=t, metadatos=dict(m or {}), score=1 - d)  # coseno: distancia -> similitud
            for t, m, d in zip(documentos, metadatos, distancias)
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

########################################################################
################  CONFIGURACION LLM MEDIANTE OLLAMA  ###################
########################################################################

class OllamaLLM(LLM):
    """Modelo local servido por Ollama"""

    def __init__(self, config: Config):
        import ollama

        self._ollama = ollama
        self._cliente = ollama.Client(host=config.ollama_host)
        self._host = config.ollama_host
        self._modelo = config.llm_model
        self._opciones = {
            "num_ctx": config.llm_num_ctx,
            "temperature": config.llm_temperature,
        }
        self._enviar_think = True  # pasa a False si el modelo no admite la opción

    def generar(self, mensajes: list[dict]) -> str:
        try:
            return self._chat(mensajes)
        except self._ollama.ResponseError as e:
            if e.status_code == 404:
                raise RuntimeError(
                    f"El modelo '{self._modelo}' no está descargado en Ollama. "
                    f"Descárgalo con: ollama pull {self._modelo}"
                ) from e
            raise RuntimeError(f"Ollama devolvió un error: {e}") from e
        except ConnectionError as e:
            raise RuntimeError(
                f"No se pudo conectar con Ollama en {self._host}. "
                "¿Está en ejecución (ollama serve)?"
            ) from e

    def _chat(self, mensajes: list[dict]) -> str:
        # Los modelos que "piensan" antes de responder gastan tiempo y tokens que
        # aquí no aportan, así que se pide desactivarlo. Si el modelo no admite
        # la opción (Granite, Ministral...), se reintenta sin ella y se recuerda
        # para no repetir el intento fallido en cada pregunta.
        think = False if self._enviar_think else None  # None = no enviar la opción
        try:
            r = self._cliente.chat(
                model=self._modelo, messages=mensajes, options=self._opciones, think=think
            )
        except self._ollama.ResponseError as e:
            if think is None or e.status_code == 404 or "think" not in str(e).lower():
                raise
            self._enviar_think = False
            r = self._cliente.chat(
                model=self._modelo, messages=mensajes, options=self._opciones
            )
        # Algunos modelos (Qwen3 en su variante "thinking") razonan aunque se pida
        # lo contrario y devuelven el razonamiento dentro de la respuesta, sin la
        # etiqueta de apertura: solo aparece el cierre </think>. Se descarta todo
        # hasta ahí.
        contenido = r["message"]["content"] or ""
        return re.sub(r"\A.*?</think>", "", contenido, count=1, flags=re.DOTALL).strip()
