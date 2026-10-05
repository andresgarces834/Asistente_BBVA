"""Prueba del servicio de chat: con qué hora se guarda cada pregunta.

Desde la raíz del repo:
    python -m unittest discover tests -v
"""

import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from src.memory.historial import HistorialSQLite
from src.rag.asistente import Respuesta
from src.rag.chat import ServicioChat


class AsistenteLento:
    """Hace de asistente: tarda un poco y siempre responde lo mismo"""

    def responder(self, pregunta, historial):
        time.sleep(1.1)
        return Respuesta(texto="respuesta")


class PruebasHoraDeLaPregunta(unittest.TestCase):
    def test_la_pregunta_se_guarda_con_la_hora_en_que_llego_y_no_con_la_de_la_respuesta(self):
        carpeta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(carpeta.cleanup)
        historial = HistorialSQLite(Path(carpeta.name) / "historial.db")
        servicio = ServicioChat(AsistenteLento(), historial, 6, "modelo")  # type: ignore[arg-type]

        servicio.responder("s", "¿hola?")

        pregunta, respuesta = historial.ultimos("s", 2)
        espera = datetime.fromisoformat(str(respuesta.creado_en)) - datetime.fromisoformat(str(pregunta.creado_en))
        # Entre una hora y otra pasó lo que tardó el asistente (1,1 s): la hora de la pregunta
        # no puede ser la misma que la de la respuesta.
        self.assertGreaterEqual(espera.total_seconds(), 1)


if __name__ == "__main__":
    unittest.main()
