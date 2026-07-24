FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend /app/backend

RUN useradd --create-home --uid 10001 gestinem \
    && mkdir -p /data/documentos \
    && chown -R gestinem:gestinem /app /data/documentos
USER gestinem

EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn backend.dgt_api.app:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
