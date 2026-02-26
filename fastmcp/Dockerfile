FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py .
CMD ["sh", "-c", "python ${MODULE:-tg_chat}.py"]
