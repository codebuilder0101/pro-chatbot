# Imagem unica para os dois processos. Qual deles roda depende do CMD.
#   agente:       docker run ... iara-server
#   token server: docker run ... iara-server token-server
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# ffmpeg/libsndfile sao exigidos pelos plugins de audio; build-essential so
# durante a instalacao, removido depois para nao inchar a imagem.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y build-essential && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY agent ./agent
COPY token_server ./token_server
COPY tests ./tests
COPY docker-entrypoint.sh ./docker-entrypoint.sh

# Baixa os pesos do VAD e do detector de fim de turno na build, nao no primeiro
# turno de conversa do primeiro usuario.
RUN python -m agent.agent download-files || \
    echo "aviso: download-files falhou na build; sera feito no boot"

RUN useradd -m -u 10001 iara && chown -R iara:iara /app
USER iara

EXPOSE 8080

ENTRYPOINT ["/bin/sh", "/app/docker-entrypoint.sh"]
CMD ["agent"]
