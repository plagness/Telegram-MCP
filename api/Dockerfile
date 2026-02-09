FROM python:3.11-slim

LABEL org.opencontainers.image.title="tgapi" \
      org.opencontainers.image.description="Telegram-MCP API service" \
      org.opencontainers.image.source="https://github.com/plagness/Telegram-MCP.git" \
      ns.module="telegram" \
      ns.component="api"

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY api/requirements.txt ./requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg62-turbo-dev zlib1g-dev libfreetype6-dev fonts-dejavu-core \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove libjpeg62-turbo-dev zlib1g-dev libfreetype6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY api/app ./app
COPY templates ./templates

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
