FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY deploy/billing-worker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY billing_worker /app/billing_worker

RUN useradd --create-home --uid 10001 billingworker \
    && chown -R billingworker:billingworker /app \
    && chmod -R 0555 /app
USER billingworker

CMD ["python", "-m", "billing_worker"]
