"""Patrón Facade (estructural): una interfaz simple sobre todo el flujo RAG.

Quien use el asistente solo llama a `responder`; no sabe
nada de embeddings, de la base vectorial, del prompt ni del LLM.

Uso rapido desde la raíz del repo:
    python -m src.rag.asistente "¿Qué requisitos pide un crédito de vivienda?"
"""

import argparse
import sys
from dataclasses import dataclass, field

from src.config import Config, obtener_config
from src.providers.base import LLM
from src.providers.factory import obtener_fabrica
from src.rag.prompt import construir_mensajes
from src.rag.retriever import Retriever

@dataclass
class Fuente:
    titulo: str
    url: str
    score: float

@dataclass
class Respuesta:
    texto: str
    fuentes: list[Fuente] = field(default_factory=list)

######################################################################
######################  CONFIGURACIÓN AL RAG  ########################
######################################################################

class AsistenteRAG:
    def __init__(self, retriever: Retriever, llm: LLM):
        self._retriever = retriever
        self._llm = llm

    @classmethod
    def desde_config(cls, config: Config | None = None) -> "AsistenteRAG":
        """Arma el asistente con los proveedores que indique la configuración"""

        config = config or obtener_config()
        fabrica = obtener_fabrica(config)
        retriever = Retriever(
            fabrica.crear_embeddings(), fabrica.crear_vector_store(), config.top_k
        )
        return cls(retriever, fabrica.crear_llm())

    def responder(self, pregunta: str, historial: list[dict] | None = None) -> Respuesta:
        """`historial`: mensajes previos [{'role', 'content'}] de la conversación"""

        fragmentos = self._retriever.recuperar(pregunta)
        mensajes = construir_mensajes(pregunta, fragmentos, historial)
        texto = self._llm.generar(mensajes)

        # Una fuente por página, con el mejor puntaje de sus fragmentos.
        fuentes: dict[str, Fuente] = {}
        for f in fragmentos:
            url = f.metadatos.get("url", "")
            if url not in fuentes:
                fuentes[url] = Fuente(f.metadatos.get("titulo", ""), url, f.score)

        return Respuesta(texto=texto.strip(), fuentes=list(fuentes.values()))

def main() -> None:
    ap = argparse.ArgumentParser(description="Hace una pregunta al asistente.")
    ap.add_argument("pregunta")
    args = ap.parse_args()

    try:
        respuesta = AsistenteRAG.desde_config().responder(args.pregunta)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(respuesta.texto)
    print("\nFuentes:")
    for f in respuesta.fuentes:
        print(f"  - {f.titulo} ({f.score:.2f}) {f.url}")

if __name__ == "__main__":
    main()