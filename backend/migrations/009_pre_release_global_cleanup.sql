-- Control de la purga global permitida exclusivamente antes de publicar Flutter.
CREATE TABLE IF NOT EXISTS msg_cleanup_policy (
  id varchar(32) PRIMARY KEY,
  publication_locked_at timestamptz,
  publication_locked_by varchar(160) NOT NULL DEFAULT '',
  maintenance_started_at timestamptz,
  maintenance_actor varchar(160) NOT NULL DEFAULT '',
  updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO msg_cleanup_policy (id)
VALUES ('pre_release')
ON CONFLICT (id) DO NOTHING;
