-- Migracion 005: trazabilidad documental completa de adjuntos de mensajeria
-- Aplica en Railway (backend) despues de desplegar la version correspondiente.
-- Es seguro ejecutarla varias veces gracias a IF NOT EXISTS / DO NOTHING.

-- ── Adjuntos: campos de retirada ────────────────────────────────────────────
ALTER TABLE msg_attachments
  ADD COLUMN IF NOT EXISTS withdrawn_at      TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS withdrawn_by      VARCHAR(64)  NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS withdrawal_reason VARCHAR(500) NOT NULL DEFAULT '';

-- ── Descargas: fecha de confirmacion de guardado completo ───────────────────
ALTER TABLE msg_downloads
  ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

-- Indice para consultar descargas completadas por adjunto rapidamente
CREATE INDEX IF NOT EXISTS idx_msg_downloads_completed
  ON msg_downloads(attachment_id, completed_at);
