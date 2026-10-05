# Imagen de la aplicación. La usan el servidor web (servicio "app") y el indexador.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/home/app/.cache/huggingface

WORKDIR /app

# PyTorch solo para CPU. El paquete por defecto de PyPI en Linux trae las librerías de CUDA
# y pesa varios GB, y los embeddings se calculan en CPU de todas formas.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

# Primero las dependencias, y después el código: así, cambiar el código no repite este paso.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Usuario sin privilegios. Las carpetas que luego se montan como volúmenes se crean aquí para
# que el volumen herede el propietario y la aplicación pueda escribir en ellas.
RUN useradd --create-home app \
    && mkdir -p data/historial "$HF_HOME" \
    && chown -R app:app /app/data /home/app

COPY --chown=app:app src ./src
COPY --chown=app:app tests ./tests

USER app
EXPOSE 8000
CMD ["python", "-m", "src.ui.api"]
