"""API web del asistente: el endpoint de chat y la página que lo usa.

Desde la raíz del repo:
    python -m src.ui.api

Abre http://127.0.0.1:8000 (puerto y dirección en API_PORT y API_HOST). La documentación
interactiva de la API está en /docs.
"""

import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException
from fastapi import Path as RutaParam
from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from src.config import obtener_config
from src.memory.historial import Mensaje
from src.rag.chat import ServicioChat

PAGINA = Path(__file__).parent / "static" / "index.html"

# El ID de conversación viaja en la URL y se guarda como texto: se limita a caracteres seguros.
PATRON_SESION = r"^[A-Za-z0-9_-]{1,64}$"

log = logging.getLogger("asistente.api")

########################################################################
##########################  FORMATO DE LA API  #########################
########################################################################

class PeticionChat(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    session_id: str = Field(pattern=PATRON_SESION, description="ID de la conversación")
    pregunta: str = Field(min_length=1, max_length=1000)


class FuenteSalida(BaseModel):
    titulo: str
    url: str
    score: float


class MensajeSalida(BaseModel):
    rol: str
    contenido: str
    creado_en: str | None = None
    fuentes: list[FuenteSalida] = []
    latencia_ms: int | None = None
    sin_respuesta: bool = False
    pregunta_reescrita: str | None = None


class HistorialSalida(BaseModel):
    session_id: str
    mensajes: list[MensajeSalida]


class SaludSalida(BaseModel):
    ok: bool
    fragmentos: int
    modelo: str
    n_mensajes: int
    detalle: str | None = None


def _salida(mensaje: Mensaje) -> MensajeSalida:
    return MensajeSalida(**asdict(mensaje))

########################################################################
###############################  LA APP  ###############################
########################################################################

def crear_app(servicio: ServicioChat | None = None) -> FastAPI:
    """Crea la app. Sin `servicio`, lo arma desde la configuración al arrancar."""

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        if servicio is None:
            # Cargar el modelo de embeddings y el LLM tarda: se hace antes de aceptar
            # peticiones para que la primera pregunta no espere.
            app.state.chat = await run_in_threadpool(ServicioChat.desde_config)
            await run_in_threadpool(app.state.chat.calentar)
        else:
            app.state.chat = servicio
        yield

    app = FastAPI(title="Asistente BBVA", lifespan=ciclo_de_vida)

    @app.get("/", include_in_schema=False)
    def pagina() -> FileResponse:
        return FileResponse(PAGINA)

    @app.post("/api/chat", response_model=MensajeSalida)
    def chat(peticion: PeticionChat, request: Request) -> MensajeSalida:
        try:
            respuesta = request.app.state.chat.responder(peticion.session_id, peticion.pregunta)
        except RuntimeError as e:
            # Ollama apagado, modelo sin descargar...: el mensaje ya dice cómo resolverlo.
            raise HTTPException(status_code=503, detail=str(e)) from e
        return _salida(respuesta)

    @app.get("/api/sesiones/{session_id}/mensajes", response_model=HistorialSalida)
    def mensajes(
        session_id: Annotated[str, RutaParam(pattern=PATRON_SESION)], request: Request
    ) -> HistorialSalida:
        guardados = request.app.state.chat.mensajes(session_id)
        return HistorialSalida(session_id=session_id, mensajes=[_salida(m) for m in guardados])

    @app.get("/api/salud", response_model=SaludSalida)
    def salud(request: Request) -> SaludSalida:
        estado = request.app.state.chat.estado()
        return SaludSalida(
            ok=estado.ok,
            fragmentos=estado.fragmentos,
            modelo=estado.modelo,
            n_mensajes=estado.n_mensajes,
            detalle=estado.error_llm,
        )

    @app.exception_handler(Exception)
    async def error_inesperado(request: Request, exc: Exception) -> JSONResponse:
        log.exception("Error inesperado en %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Error interno del servidor. Revisa los registros."},
        )

    return app

app = crear_app()

def main() -> None:
    import uvicorn

    config = obtener_config()
    uvicorn.run(app, host=config.api_host, port=config.api_port)

if __name__ == "__main__":
    main()
