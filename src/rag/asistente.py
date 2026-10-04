"""Patrón Facade (estructural): una interfaz simple sobre todo el flujo RAG.

Quien use el asistente solo llama a `responder`; no sabe
nada de embeddings, de la base vectorial, del prompt ni del LLM.

Uso rápido desde la raíz del repo:
    python -m src.rag.asistente "¿Qué requisitos pide un crédito de vivienda?"
"""

import argparse
import re
import sys
from dataclasses import dataclass, field

from src.config import Config, obtener_config
from src.providers.base import LLM
from src.providers.factory import obtener_fabrica
from src.rag.prompt import construir_mensajes, construir_mensajes_reescritura
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
    # La pregunta autónoma con la que se buscó, cuando hubo que reescribirla.
    pregunta_reescrita: str | None = None

@dataclass
class Estado:
    fragmentos: int                 # fragmentos indexados en la base vectorial
    error_llm: str | None = None    # None si el modelo está disponible; si no, qué hacer

######################################################################
######################  CONFIGURACIÓN AL RAG  ########################
######################################################################

class AsistenteRAG:
    def __init__(self, retriever: Retriever, llm: LLM, reescribir: bool = True):
        self._retriever = retriever
        self._llm = llm
        self._reescribir = reescribir

    @classmethod
    def desde_config(cls, config: Config | None = None) -> "AsistenteRAG":
        """Arma el asistente con los proveedores que indique la configuración"""

        config = config or obtener_config()
        fabrica = obtener_fabrica(config)
        retriever = Retriever(
            fabrica.crear_embeddings(), fabrica.crear_vector_store(), config.top_k
        )
        return cls(retriever, fabrica.crear_llm(), config.reescribir_preguntas)

    def responder(self, pregunta: str, historial: list[dict] | None = None) -> Respuesta:
        """`historial`: mensajes previos [{'role', 'content'}] de la conversación"""

        # La búsqueda no ve el historial: una pregunta de seguimiento ("¿y la del plan
        # plus?") no dice de qué producto habla. Por eso se reescribe antes de buscar.
        consulta = pregunta
        if historial and self._reescribir:
            consulta = self._reescribir_pregunta(pregunta, historial)

        fragmentos = self._retriever.recuperar(consulta)
        mensajes = construir_mensajes(pregunta, fragmentos, historial)
        texto = self._llm.generar(mensajes)

        # Una fuente por página, con el mejor puntaje de sus fragmentos.
        fuentes: dict[str, Fuente] = {}
        for f in fragmentos:
            url = f.metadatos.get("url", "")
            if url not in fuentes:
                fuentes[url] = Fuente(f.metadatos.get("titulo", ""), url, f.score)

        return Respuesta(
            texto=texto.strip(),
            fuentes=list(fuentes.values()),
            pregunta_reescrita=consulta if consulta != pregunta else None,
        )

    def _reescribir_pregunta(self, pregunta: str, historial: list[dict]) -> str:
        """Convierte una pregunta de seguimiento en una que se entiende sola.

        Si el modelo devuelve algo inservible (vacío o mucho más largo que la pregunta),
        se usa la pregunta original.
        """

        respuesta = self._llm.generar(construir_mensajes_reescritura(pregunta, historial))

        lineas = respuesta.strip().splitlines()
        candidata = lineas[0].strip().strip('"“”«»').strip() if lineas else ""
        candidata = re.sub(r"^pregunta reescrita\s*:\s*", "", candidata, flags=re.IGNORECASE)

        if not candidata or len(candidata) > max(300, 3 * len(pregunta)):
            return pregunta
        return candidata

    def calentar(self) -> None:
        """Carga el modelo de embeddings y el LLM, para que la primera pregunta no espere"""

        self._retriever.recuperar("calentamiento")
        try:
            self._llm.generar([{"role": "user", "content": "Responde solo: ok"}])
        except RuntimeError:
            pass  # sin Ollama el error saldrá en la primera pregunta y en `estado()`

    def estado(self) -> Estado:
        """Resumen para comprobar que todo está listo: fragmentos indexados y LLM"""

        try:
            self._llm.verificar()
        except RuntimeError as e:
            return Estado(self._retriever.contar(), str(e))
        return Estado(self._retriever.contar())

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
