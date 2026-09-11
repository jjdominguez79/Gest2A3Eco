FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright \
    && rm /tmp/requirements.txt

COPY aapp_worker /app/aapp_worker
COPY services /app/services
COPY utils /app/utils

RUN useradd --create-home --uid 10001 aappworker \
    && mkdir -p /data/diagnostico \
    && chown -R aappworker:aappworker /app /data/diagnostico \
    && chmod -R 0555 /app

USER aappworker

CMD ["python", "-m", "aapp_worker"]
