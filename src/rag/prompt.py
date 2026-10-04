"""Construcción del prompt: instrucciones + contexto recuperado + historial + pregunta."""

from src.providers.base import Resultado

SISTEM_PROMPT = (
    """ 
    Eres un asistente que responde preguntas sobre el sitio web público de BBVA Colombia.

    Reglas:

    - Responde SOLO con la información de los fragmentos de contexto que se te 
    entregan.
    - Si los fragmentos no contienen la respuesta, responde exactamente: 
    \"No encontré esa información en el sitio de BBVA Colombia.\" No inventes cifras, tasas, requisitos ni condiciones.
    - Si el usuario solo saluda o se despide, responde con un saludo breve e invítalo a preguntar sobre los productos y servicios de BBVA Colombia.
    - Responde en español, de forma clara y breve.
    - Cuando uses información de un fragmento, menciona el título de su página entre corchetes, por ejemplo [Cuenta de Ahorro Blue].
    - Si la pregunta es de seguimiento, usa la conversación previa para entenderla.
    """
)

def formatear_contexto(fragmentos: list[Resultado]) -> str:
    if not fragmentos:
        return "(sin fragmentos relevantes)"

    return "\n\n".join(
        f"[{i}] {f.metadatos.get('titulo', '')} ({f.metadatos.get('url', '')})\n{f.texto}"
        for i, f in enumerate(fragmentos, 1)
    )

def construir_mensajes(pregunta: str, fragmentos: list[Resultado],
                       historial: list[dict] | None = None) -> list[dict]:
    """Mensajes en el formato de chat: sistema, historial previo y la pregunta con su contexto"""

    usuario = f"Contexto:\n{formatear_contexto(fragmentos)}\n\nPregunta: {pregunta}"

    return [
        {"role": "system", "content": SISTEM_PROMPT},
        *(historial or []),
        {"role": "user", "content": usuario},
    ]
