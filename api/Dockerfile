FROM python:3.11-slim

LABEL org.opencontainers.image.title="tgapi" \
      org.opencontainers.image.description="Telegram-MCP API service" \
      org.opencontainers.image.source="https://github.com/plagness/Telegram-MCP.git" \
      ns.module="telegram" \
      ns.component="api"

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY api/app ./app
COPY templates ./templates

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
