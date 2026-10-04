"""Conversacion asistente RAG con el historial de cada sesión.

Cada pregunta se responde teniendo en cuenta los últimos N mensajes de su sesión, y el
intercambio se guarda al terminar. La fachada `AsistenteRAG` sigue sin guardar estado: 
quien lleva el historial es este servicio.
"""

import threading
import time
from dataclasses import dataclass

from src.config import Config, obtener_config
from src.memory.historial import Historial, Mensaje
from src.providers.factory import obtener_fabrica
from src.rag.asistente import AsistenteRAG
from src.rag.prompt import es_sin_respuesta

@dataclass
class EstadoChat:
    fragmentos: int
    modelo: str
    n_mensajes: int
    error_llm: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_llm is None and self.fragmentos > 0

class ServicioChat:
    def __init__(self, asistente: AsistenteRAG, historial: Historial,
                 n_mensajes: int, modelo: str):
        self._asistente = asistente
        self._historial = historial
        self._n_mensajes = n_mensajes
        self._modelo = modelo
        # El modelo atiende de uno en uno y así cada intercambio se guarda completo y en orden.
        self._candado = threading.Lock()

    @classmethod
    def desde_config(cls, config: Config | None = None) -> "ServicioChat":
        config = config or obtener_config()
        fabrica = obtener_fabrica(config)
        return cls(
            AsistenteRAG.desde_config(config),
            fabrica.crear_historial(),
            config.n_mensajes,
            config.llm_model,
        )

    def responder(self, session_id: str, pregunta: str) -> Mensaje:
        """Responde dentro de la conversación `session_id` y devuelve el mensaje del asistente"""

        with self._candado:
            previos = self._contexto(session_id)

            inicio = time.perf_counter()
            r = self._asistente.responder(pregunta, previos)
            latencia_ms = int((time.perf_counter() - inicio) * 1000)

            respuesta = Mensaje(
                rol="assistant",
                contenido=r.texto,
                fuentes=[
                    {"titulo": f.titulo, "url": f.url, "score": round(f.score, 3)}
                    for f in r.fuentes
                ],
                modelo=self._modelo,
                latencia_ms=latencia_ms,
                sin_respuesta=es_sin_respuesta(r.texto),
                pregunta_reescrita=r.pregunta_reescrita,
            )

            # Se guarda solo si todo salió bien: si el modelo falla, la conversacion no queda con una pregunta sin respuesta.
            self._historial.agregar(session_id, [Mensaje(rol="user", contenido=pregunta), respuesta])
            return respuesta

    def mensajes(self, session_id: str, limite: int = 100) -> list[Mensaje]:
        """Los últimos mensajes de una conversación, para mostrarla de nuevo"""

        return self._historial.ultimos(session_id, limite)

    def calentar(self) -> None:
        self._asistente.calentar()

    def estado(self) -> EstadoChat:
        estado = self._asistente.estado()
        return EstadoChat(estado.fragmentos, self._modelo, self._n_mensajes, estado.error_llm)

    def _contexto(self, session_id: str) -> list[dict]:
        mensajes = self._historial.ultimos(session_id, self._n_mensajes)

        # La ventana debe empezar con un mensaje del usuario, no con media conversación.
        while mensajes and mensajes[0].rol != "user":
            mensajes.pop(0)

        return [{"role": m.rol, "content": m.contenido} for m in mensajes]
