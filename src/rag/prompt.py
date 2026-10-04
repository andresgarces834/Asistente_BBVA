"""Construcción del prompt: instrucciones + contexto recuperado + historial + pregunta."""

from src.providers.base import Resultado

# Frase exacta con la que el asistente declara que no encontró la respuesta. Se usa en
# el prompt y también para detectar esas respuestas (métricas del historial).
SIN_RESPUESTA = "No encontré esa información en el sitio de BBVA Colombia."

def es_sin_respuesta(texto: str) -> bool:
    """¿La respuesta dice que no encontró la información? (tolera cambios de puntuación)"""

    return SIN_RESPUESTA.rstrip(".").lower() in texto.lower()

SISTEM_PROMPT = (
    f""" 
    Eres un asistente que responde preguntas sobre el sitio web público de BBVA Colombia.

    Reglas:

    - Responde SOLO con la información de los fragmentos de contexto que se te 
    entregan.
    - Si los fragmentos no contienen la respuesta, responde exactamente: 
    \"{SIN_RESPUESTA}\" No inventes cifras, tasas, requisitos ni condiciones.
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

########################################################################
#####################  REESCRITURA DE PREGUNTAS  #######################
########################################################################

SISTEMA_REESCRITURA = (
    "Reescribe la última pregunta del usuario para que se entienda sin la conversación "
    "previa.\n"
    "- Usa la conversación para completar lo que falta, sobre todo el producto o el tema "
    "concreto al que se refiere (por ejemplo, el nombre de la cuenta o de la tarjeta).\n"
    "- No respondas la pregunta ni añadas información nueva.\n"
    "- Si la pregunta ya se entiende sola, devuélvela igual.\n"
    "- Responde únicamente con la pregunta reescrita, en español."
)

# De cada mensaje previo solo se envía el principio: basta para saber de qué se habla.
MAX_CARACTERES_MENSAJE = 500

def construir_mensajes_reescritura(pregunta: str, historial: list[dict]) -> list[dict]:
    """Mensajes para convertir una pregunta de seguimiento en una pregunta autónoma"""

    conversacion = "\n".join(
        f"{'Usuario' if m['role'] == 'user' else 'Asistente'}: {m['content'][:MAX_CARACTERES_MENSAJE]}"
        for m in historial
    )
    usuario = (
        f"Conversación previa:\n{conversacion}\n\n"
        f"Última pregunta del usuario: {pregunta}\n\n"
        "Pregunta reescrita:"
    )

    return [
        {"role": "system", "content": SISTEMA_REESCRITURA},
        {"role": "user", "content": usuario},
    ]
