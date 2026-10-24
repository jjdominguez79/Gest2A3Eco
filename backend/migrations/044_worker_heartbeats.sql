-- 044_worker_heartbeats.sql
-- Etapa 5 de la facturacion autonoma de clientes (ver docs/adr/0001).
--
-- Observabilidad minima (seccion 22 del encargo): saber si billing_worker e
-- invoice_worker estan vivos y cuando se les vio por ultima vez. Una fila
-- por nombre de worker (no por instancia/replica): el objetivo es "hay al
-- menos una instancia viva", no inventariar replicas.

CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_name VARCHAR(60) PRIMARY KEY,
    instance_id VARCHAR(120) NOT NULL DEFAULT '',
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    jobs_processed_total INTEGER NOT NULL DEFAULT 0,
    jobs_failed_total INTEGER NOT NULL DEFAULT 0,
    status_detail TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_worker_heartbeats_last_seen ON worker_heartbeats(last_seen_at);
