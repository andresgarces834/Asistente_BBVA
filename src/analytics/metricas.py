"""Métricas del historial de conversaciones.

Recorre todas las conversaciones guardadas y calcula cinco métricas:
  - número de conversaciones
  - mensajes por conversación
  - turnos usuario-asistente
  - longitud promedio de los mensajes
  - duración de la conversación

Desde la raíz del repo:
    python -m src.analytics.metricas
    python -m src.analytics.metricas --db data/historial/otro.db
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

from src.config import RAIZ, obtener_config
from src.memory.historial import Historial, HistorialSQLite, Mensaje

ANCHO = 44  # ancho de la columna de etiquetas del reporte

########################################################################
##############################  CALCULAR  ##############################
########################################################################

def agrupar(historial: Historial) -> dict[str, list[Mensaje]]:
    """Los mensajes de cada conversación, en orden, según su ID de sesión"""

    conversaciones: dict[str, list[Mensaje]] = {}
    for session_id, mensaje in historial.todos():
        conversaciones.setdefault(session_id, []).append(mensaje)
    return conversaciones


def contar_turnos(mensajes: list[Mensaje]) -> int:
    """Un turno es una pregunta del usuario seguida de la respuesta del asistente"""

    return sum(
        1 for anterior, siguiente in zip(mensajes, mensajes[1:])
        if anterior.rol == "user" and siguiente.rol == "assistant"
    )


def duracion_s(mensajes: list[Mensaje]) -> float:
    """Segundos entre el primer y el último mensaje de la conversación"""

    momentos = [datetime.fromisoformat(m.creado_en) for m in mensajes if m.creado_en]
    return (max(momentos) - min(momentos)).total_seconds() if momentos else 0.0


def _resumen(valores: Sequence[float]) -> dict[str, float]:
    return {"promedio": mean(valores), "minimo": min(valores), "maximo": max(valores)}


def calcular(conversaciones: dict[str, list[Mensaje]]) -> dict[str, Any]:
    """Las cinco métricas. Las longitudes están en caracteres y las duraciones en segundos."""

    if not conversaciones:
        return {"conversaciones": 0}

    listas = list(conversaciones.values())
    turnos = [contar_turnos(mensajes) for mensajes in listas]
    todos = [m for mensajes in listas for m in mensajes]
    del_usuario = [len(m.contenido) for m in todos if m.rol == "user"]
    del_asistente = [len(m.contenido) for m in todos if m.rol == "assistant"]

    return {
        "conversaciones": len(conversaciones),
        "mensajes_por_conversacion": _resumen([len(mensajes) for mensajes in listas]),
        "turnos": {"total": sum(turnos), **_resumen(turnos)},
        # Por separado: un solo promedio mezclaría preguntas cortas con respuestas largas.
        "longitud_promedio": {
            "usuario": mean(del_usuario) if del_usuario else None,
            "asistente": mean(del_asistente) if del_asistente else None,
        },
        "duracion_s": _resumen([duracion_s(mensajes) for mensajes in listas]),
    }

########################################################################
##############################  PRESENTAR  #############################
########################################################################

def _num(valor: float) -> str:
    """Un decimal con coma: 3.5 -> 3,5"""

    return f"{valor:.1f}".replace(".", ",")


def _duracion(segundos: float) -> str:
    segundos = round(segundos)
    return f"{segundos // 60} min {segundos % 60} s" if segundos >= 60 else f"{segundos} s"


def _fila(etiqueta: str, valor: str) -> str:
    return f"{etiqueta} ".ljust(ANCHO, ".") + f" {valor}"


def formatear(m: dict[str, Any]) -> str:
    """El reporte en texto"""

    if m["conversaciones"] == 0:
        return "No hay conversaciones guardadas."

    mensajes, turnos, duracion = m["mensajes_por_conversacion"], m["turnos"], m["duracion_s"]
    longitud = " | ".join(
        f"{rol} {round(valor)} caracteres"
        for rol, valor in m["longitud_promedio"].items() if valor is not None
    )

    return "\n".join([
        _fila("Conversaciones", str(m["conversaciones"])),
        _fila("Mensajes por conversación",
              f"promedio {_num(mensajes['promedio'])} | mínimo {mensajes['minimo']}"
              f" | máximo {mensajes['maximo']}"),
        _fila("Turnos usuario-asistente",
              f"{turnos['total']} en total | promedio {_num(turnos['promedio'])} por conversación"
              f" | máximo {turnos['maximo']}"),
        _fila("Longitud promedio de los mensajes", longitud),
        _fila("Duración de la conversación",
              f"promedio {_duracion(duracion['promedio'])} | máxima {_duracion(duracion['maximo'])}"),
    ])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Métricas del historial de conversaciones.")
    ap.add_argument("--db", help="archivo SQLite del historial (por defecto, el de HISTORIAL_PATH)")
    args = ap.parse_args(argv)

    ruta = Path(args.db) if args.db else RAIZ / obtener_config().historial_path
    if not ruta.exists():  # sin esto, un error al escribir la ruta crearía una base vacía
        print(f"Error: no existe el historial en {ruta}. Crea conversaciones desde el chat.",
              file=sys.stderr)
        return 1

    print(f"Base: {ruta}\n")
    print(formatear(calcular(agrupar(HistorialSQLite(ruta)))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
