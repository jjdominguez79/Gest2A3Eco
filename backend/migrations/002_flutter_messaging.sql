-- Extensiones aditivas de mensajeria para Gestinem Flutter.
ALTER TABLE msg_messages ADD COLUMN IF NOT EXISTS reply_to_message_id varchar(36) REFERENCES msg_messages(id) ON DELETE SET NULL;
ALTER TABLE msg_messages ADD COLUMN IF NOT EXISTS deleted_at timestamptz;
ALTER TABLE msg_messages ADD COLUMN IF NOT EXISTS deleted_by varchar(64) NOT NULL DEFAULT '';
ALTER TABLE msg_messages ADD COLUMN IF NOT EXISTS deleted_by_type varchar(16) NOT NULL DEFAULT '';
ALTER TABLE msg_messages ADD COLUMN IF NOT EXISTS delete_reason varchar(500) NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS ix_msg_messages_reply_to_message_id ON msg_messages(reply_to_message_id);

ALTER TABLE msg_staff_thread_messages ADD COLUMN IF NOT EXISTS reply_to_message_id varchar(36) REFERENCES msg_staff_thread_messages(id) ON DELETE SET NULL;
ALTER TABLE msg_staff_thread_messages ADD COLUMN IF NOT EXISTS deleted_at timestamptz;
ALTER TABLE msg_staff_thread_messages ADD COLUMN IF NOT EXISTS deleted_by varchar(64) NOT NULL DEFAULT '';
ALTER TABLE msg_staff_thread_messages ADD COLUMN IF NOT EXISTS deleted_by_type varchar(16) NOT NULL DEFAULT '';
ALTER TABLE msg_staff_thread_messages ADD COLUMN IF NOT EXISTS delete_reason varchar(500) NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS ix_msg_staff_thread_messages_reply_to_message_id ON msg_staff_thread_messages(reply_to_message_id);

CREATE TABLE IF NOT EXISTS msg_groups (id varchar(36) PRIMARY KEY, name varchar(160) NOT NULL, description text NOT NULL DEFAULT '', group_type varchar(20) NOT NULL, created_by varchar(64) NOT NULL, active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS ix_msg_groups_group_type ON msg_groups(group_type);
CREATE TABLE IF NOT EXISTS msg_group_members (id varchar(36) PRIMARY KEY, group_id varchar(36) NOT NULL REFERENCES msg_groups(id) ON DELETE CASCADE, member_type varchar(16) NOT NULL, member_id varchar(64) NOT NULL, role varchar(20) NOT NULL DEFAULT 'member', created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(group_id, member_type, member_id));
CREATE INDEX IF NOT EXISTS ix_msg_group_members_member ON msg_group_members(member_type, member_id);

CREATE TABLE IF NOT EXISTS msg_campaigns (id varchar(36) PRIMARY KEY, name varchar(160) NOT NULL, body text NOT NULL, channel varchar(20) NOT NULL DEFAULT 'fiscal', created_by varchar(64) NOT NULL, status varchar(20) NOT NULL DEFAULT 'draft', created_at timestamptz NOT NULL DEFAULT now(), scheduled_at timestamptz, sent_at timestamptz);
CREATE TABLE IF NOT EXISTS msg_campaign_recipients (id varchar(36) PRIMARY KEY, campaign_id varchar(36) NOT NULL REFERENCES msg_campaigns(id) ON DELETE CASCADE, client_id varchar(36) NOT NULL REFERENCES msg_clients(id) ON DELETE CASCADE, status varchar(20) NOT NULL DEFAULT 'pending', message_id varchar(36) REFERENCES msg_messages(id) ON DELETE SET NULL, error text NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now(), sent_at timestamptz, read_at timestamptz, UNIQUE(campaign_id, client_id));
CREATE INDEX IF NOT EXISTS ix_msg_campaign_recipients_status ON msg_campaign_recipients(campaign_id, status);

CREATE TABLE IF NOT EXISTS msg_app_devices (id varchar(36) PRIMARY KEY, user_type varchar(16) NOT NULL, user_id varchar(64) NOT NULL, platform varchar(16) NOT NULL, push_token text UNIQUE NOT NULL, device_name varchar(160) NOT NULL DEFAULT '', app_version varchar(40) NOT NULL DEFAULT '', active boolean NOT NULL DEFAULT true, active_conversation_id varchar(36) NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), last_seen_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS ix_msg_app_devices_user ON msg_app_devices(user_type, user_id, active);
CREATE TABLE IF NOT EXISTS msg_deletion_audit (id varchar(36) PRIMARY KEY, message_id varchar(36) NOT NULL, conversation_id varchar(36) NOT NULL, actor_id varchar(64) NOT NULL, action varchar(16) NOT NULL, reason varchar(500) NOT NULL DEFAULT '', attachment_count integer NOT NULL DEFAULT 0, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS msg_staff_app_codes (id varchar(36) PRIMARY KEY, staff_external_id varchar(64) NOT NULL REFERENCES msg_staff(external_id) ON DELETE CASCADE, code_hash varchar(64) UNIQUE NOT NULL, expires_at timestamptz NOT NULL, used_at timestamptz, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS msg_websocket_tickets (id varchar(36) PRIMARY KEY, user_type varchar(16) NOT NULL, user_id varchar(64) NOT NULL, token_hash varchar(64) UNIQUE NOT NULL, expires_at timestamptz NOT NULL, used_at timestamptz, created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS ix_msg_websocket_tickets_expiry ON msg_websocket_tickets(expires_at);
