"""Pruebas de las métricas del historial.

Desde la raíz del repo:
    python -m unittest discover tests -v

Los datos están inventados a mano: cada número esperado se comprueba con una cuenta sencilla.
No hace falta Ollama ni el índice.
"""

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from src.analytics import metricas
from src.memory.historial import HistorialSQLite, Mensaje


def mensaje(rol: str, texto: str, hora: str) -> Mensaje:
    return Mensaje(rol, texto, f"2026-10-04T{hora}+00:00")


def base_temporal(prueba: unittest.TestCase) -> Path:
    """Ruta de una base nueva, en una carpeta que se borra sola al terminar la prueba"""

    carpeta = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    prueba.addCleanup(carpeta.cleanup)
    return Path(carpeta.name) / "historial.db"


# La conversación "a" tiene 4 mensajes (2 turnos) y la "b" tiene 2 (1 turno).
CONVERSACIONES = {
    "a": [
        mensaje("user", "hola", "10:00:00"),                # 4 caracteres
        mensaje("assistant", "buenas tardes", "10:00:05"),  # 13
        mensaje("user", "ok", "10:01:00"),                  # 2
        mensaje("assistant", "listo!!", "10:01:10"),        # 7
    ],
    "b": [
        mensaje("user", "pregunta", "11:00:00"),              # 8
        mensaje("assistant", "respuesta larga", "11:00:10"),  # 15
    ],
}

########################################################################
##########################  LAS CINCO MÉTRICAS  ########################
########################################################################

class PruebasCalcular(unittest.TestCase):
    def setUp(self):
        self.m = metricas.calcular(CONVERSACIONES)

    def test_conversaciones(self):
        self.assertEqual(self.m["conversaciones"], 2)

    def test_mensajes_por_conversacion(self):
        # "a" tiene 4 mensajes y "b" tiene 2.
        self.assertEqual(self.m["mensajes_por_conversacion"], {"promedio": 3, "minimo": 2, "maximo": 4})

    def test_turnos(self):
        # "a" tiene 2 turnos y "b" tiene 1.
        self.assertEqual(self.m["turnos"], {"total": 3, "promedio": 1.5, "minimo": 1, "maximo": 2})

    def test_longitud_promedio_por_rol(self):
        # Usuario: (4 + 2 + 8) / 3. Asistente: (13 + 7 + 15) / 3.
        longitud = self.m["longitud_promedio"]
        self.assertAlmostEqual(longitud["usuario"], 14 / 3)
        self.assertAlmostEqual(longitud["asistente"], 35 / 3)

    def test_duracion(self):
        # "a" va de 10:00:00 a 10:01:10 (70 s) y "b" de 11:00:00 a 11:00:10 (10 s).
        self.assertEqual(self.m["duracion_s"], {"promedio": 40, "minimo": 10, "maximo": 70})


class PruebasCasosLimite(unittest.TestCase):
    def test_sin_conversaciones(self):
        m = metricas.calcular({})
        self.assertEqual(m, {"conversaciones": 0})
        self.assertIn("No hay conversaciones", metricas.formatear(m))

    def test_una_pregunta_sin_respuesta_no_es_un_turno(self):
        self.assertEqual(metricas.contar_turnos([mensaje("user", "p", "10:00:00")]), 0)

    def test_dos_preguntas_seguidas_solo_cuentan_la_que_se_respondio(self):
        mensajes = [mensaje("user", "p1", "10:00:00"), mensaje("user", "p2", "10:00:05"),
                    mensaje("assistant", "r2", "10:00:10")]
        self.assertEqual(metricas.contar_turnos(mensajes), 1)

    def test_una_conversacion_de_un_solo_mensaje_dura_cero(self):
        self.assertEqual(metricas.duracion_s([mensaje("user", "p", "10:00:00")]), 0)

    def test_si_falta_un_rol_su_promedio_no_se_define_y_el_reporte_no_falla(self):
        m = metricas.calcular({"a": [mensaje("user", "p", "10:00:00")]})
        self.assertEqual(m["longitud_promedio"], {"usuario": 1, "asistente": None})
        self.assertRegex(metricas.formatear(m), r"Longitud promedio de los mensajes \.+ usuario 1 caracteres\n")

########################################################################
#############################  EL HISTORIAL  ###########################
########################################################################

class PruebasHistorial(unittest.TestCase):
    def test_todos_recorre_todas_las_conversaciones_en_el_orden_en_que_se_guardaron(self):
        historial = HistorialSQLite(base_temporal(self))
        historial.agregar("a", [mensaje("user", "a1", "10:00:00")])
        historial.agregar("b", [mensaje("user", "b1", "10:00:01")])
        historial.agregar("a", [mensaje("assistant", "a2", "10:00:02")])

        recorrido = [(sesion, m.contenido) for sesion, m in historial.todos()]
        self.assertEqual(recorrido, [("a", "a1"), ("b", "b1"), ("a", "a2")])

    def test_agrupar_junta_los_mensajes_de_cada_conversacion_aunque_se_guardaran_mezclados(self):
        historial = HistorialSQLite(base_temporal(self))
        historial.agregar("a", [mensaje("user", "a1", "10:00:00")])
        historial.agregar("b", [mensaje("user", "b1", "10:00:01")])
        historial.agregar("a", [mensaje("assistant", "a2", "10:00:02")])

        grupos = {sesion: [m.contenido for m in ms] for sesion, ms in metricas.agrupar(historial).items()}
        self.assertEqual(grupos, {"a": ["a1", "a2"], "b": ["b1"]})

    def test_historial_vacio(self):
        self.assertEqual(metricas.agrupar(HistorialSQLite(base_temporal(self))), {})

########################################################################
#############################  EL COMANDO  #############################
########################################################################

class PruebasComando(unittest.TestCase):
    def ejecutar(self, *argumentos: str) -> tuple[int, str, str]:
        salida, error = io.StringIO(), io.StringIO()
        with redirect_stdout(salida), redirect_stderr(error):
            codigo = metricas.main(list(argumentos))
        return codigo, salida.getvalue(), error.getvalue()

    def test_muestra_las_cinco_metricas(self):
        ruta = base_temporal(self)
        historial = HistorialSQLite(ruta)
        for sesion, mensajes in CONVERSACIONES.items():
            historial.agregar(sesion, mensajes)

        codigo, salida, error = self.ejecutar("--db", str(ruta))

        self.assertEqual((codigo, error), (0, ""))
        self.assertRegex(salida, r"Conversaciones \.+ 2\n")
        self.assertRegex(salida, r"Mensajes por conversación \.+ promedio 3,0 \| mínimo 2 \| máximo 4\n")
        self.assertRegex(salida, r"Turnos usuario-asistente \.+ 3 en total \| promedio 1,5 por conversación \| máximo 2\n")
        self.assertRegex(salida, r"Longitud promedio de los mensajes \.+ usuario 5 caracteres \| asistente 12 caracteres\n")
        self.assertRegex(salida, r"Duración de la conversación \.+ promedio 40 s \| máxima 1 min 10 s")

    def test_una_base_que_no_existe_da_error_y_no_se_crea(self):
        falsa = base_temporal(self)
        codigo, _, error = self.ejecutar("--db", str(falsa))

        self.assertEqual(codigo, 1)
        self.assertIn("no existe el historial", error)
        self.assertFalse(falsa.exists())


if __name__ == "__main__":
    unittest.main()
