"""Historial de conversaciones, guardado por ID de sesión.

Patrón Repository: `Historial` define cómo se guardan y se leen los mensajes sin decir
dónde; `HistorialSQLite` es la implementación local. El resto del sistema solo conoce 
la interfaz, así que cambiar de SQLite a otra base no lo toca.

Cada respuesta del asistente se guarda con los datos que luego sirven para analizar el
uso: qué páginas citó, qué modelo la generó, cuánto tardó, si dijo que no encontró la
información y cómo se reescribió la pregunta.
"""

import json
import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

########################################################################
######################  CLASE PARA LOS MENSAJES  #######################
########################################################################

@dataclass
class Mensaje:
    rol: str                      # "user" o "assistant", como en el formato de chat
    contenido: str
    creado_en: str | None = None  # ISO 8601 en UTC - si falta lo pone el repositorio

    # Solo para las respuestas del asistente:
    fuentes: list[dict] = field(default_factory=list)  # [{"titulo", "url", "score"}]
    modelo: str | None = None
    latencia_ms: int | None = None
    sin_respuesta: bool = False   # dijo que no encontró la información en el sitio
    pregunta_reescrita: str | None = None  # la pregunta autónoma con la que se buscó

########################################################################
######################  CLASE PARA EL HISTORIAL  #######################
########################################################################

class Historial(ABC):
    @abstractmethod
    def agregar(self, session_id: str, mensajes: list[Mensaje]) -> None:
        """Guarda los mensajes al final de la conversación, en ese orden"""

    @abstractmethod
    def ultimos(self, session_id: str, n: int) -> list[Mensaje]:
        """Los últimos `n` mensajes de la conversación, del más antiguo al más reciente"""

    @abstractmethod
    def todos(self) -> Iterator[tuple[str, Mensaje]]:
        """Recorre los mensajes de todas las conversaciones, en el orden en que se guardaron.

        Devuelve pares (session_id, mensaje). Es lo que usa el análisis del historial.
        """

########################################################################
###############  ESQUEMA DE LA BASE DE DATOS HISTORIAL  ################
########################################################################

ESQUEMA = """
CREATE TABLE IF NOT EXISTS mensajes (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id         TEXT    NOT NULL,
    rol                TEXT    NOT NULL CHECK (rol IN ('user', 'assistant')),
    contenido          TEXT    NOT NULL,
    creado_en          TEXT    NOT NULL,
    fuentes            TEXT,
    modelo             TEXT,
    latencia_ms        INTEGER,
    sin_respuesta      INTEGER NOT NULL DEFAULT 0,
    pregunta_reescrita TEXT
);
CREATE INDEX IF NOT EXISTS idx_mensajes_sesion ON mensajes (session_id, id);
"""

########################################################################
###############  IMPLEMENTACIÓN DE HISTORIAL EN SQLITE  ################
########################################################################

class HistorialSQLite(Historial):
    def __init__(self, ruta: Path):
        self._ruta = Path(ruta)
        self._ruta.parent.mkdir(parents=True, exist_ok=True)

        with closing(self._conectar()) as con:
            con.execute("PRAGMA journal_mode=WAL")  # varias lecturas mientras se escribe
            con.executescript(ESQUEMA)

    def _conectar(self) -> sqlite3.Connection:
        # Una conexión por operación: las peticiones web llegan desde hilos distintos.
        con = sqlite3.connect(self._ruta, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def agregar(self, session_id: str, mensajes: list[Mensaje]) -> None:
        ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        filas = [
            (
                session_id,
                m.rol,
                m.contenido,
                m.creado_en or ahora,
                json.dumps(m.fuentes, ensure_ascii=False) if m.fuentes else None,
                m.modelo,
                m.latencia_ms,
                int(m.sin_respuesta),
                m.pregunta_reescrita,
            )
            for m in mensajes
        ]

        # El segundo `con` es la transacción: confirma al salir, o deshace si hubo error.
        with closing(self._conectar()) as con, con:
            con.executemany(
                "INSERT INTO mensajes (session_id, rol, contenido, creado_en, fuentes, modelo,"
                " latencia_ms, sin_respuesta, pregunta_reescrita) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                filas,
            )

    def ultimos(self, session_id: str, n: int) -> list[Mensaje]:
        if n <= 0:
            return []

        with closing(self._conectar()) as con:
            filas = con.execute(
                "SELECT * FROM mensajes WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, n),
            ).fetchall()

        return [self._a_mensaje(fila) for fila in reversed(filas)]

    def todos(self) -> Iterator[tuple[str, Mensaje]]:
        # Se recorre fila a fila, sin cargar todo en memoria, y la conexión se cierra al terminar.
        with closing(self._conectar()) as con:
            for fila in con.execute("SELECT * FROM mensajes ORDER BY id"):
                yield fila["session_id"], self._a_mensaje(fila)

    @staticmethod
    def _a_mensaje(fila: sqlite3.Row) -> Mensaje:
        return Mensaje(
            rol=fila["rol"],
            contenido=fila["contenido"],
            creado_en=fila["creado_en"],
            fuentes=json.loads(fila["fuentes"]) if fila["fuentes"] else [],
            modelo=fila["modelo"],
            latencia_ms=fila["latencia_ms"],
            sin_respuesta=bool(fila["sin_respuesta"]),
            pregunta_reescrita=fila["pregunta_reescrita"],
        )
