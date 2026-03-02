FROM python:3.12-slim

RUN pip install --no-cache-dir temporalio httpx

WORKDIR /app
COPY worker.py .
COPY prompts/ ./prompts/

CMD ["python", "worker.py"]
