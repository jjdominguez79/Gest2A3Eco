from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    internal_api_key: str
    public_base_url: str
    token_ttl_hours: int
    storage_dir: str
    signrequest_token: str
    signrequest_from_email: str
    signrequest_gestor_email: str
    signrequest_gestor_telefono: str
    signrequest_base_url: str
    dataprius_api_key: str
    dataprius_api_secret: str
    dataprius_base_url: str
    dataprius_base_path: str
    messaging_public_base_url: str
    messaging_storage_dir: str
    messaging_azure_connection_string: str
    messaging_azure_container: str
    messaging_attachment_days: int
    messaging_graph_tenant_id: str
    messaging_graph_client_id: str
    messaging_graph_client_secret: str
    messaging_graph_from: str
    messaging_graph_invitation_from: str
    messaging_staff_tenant_id: str
    messaging_staff_client_id: str
    messaging_staff_client_secret: str
    messaging_staff_admin_emails: str
    messaging_staff_allowed_domain: str
    messaging_sync_token: str
    messaging_vapid_public_key: str
    messaging_vapid_private_key: str
    messaging_vapid_subject: str
    messaging_smtp_host: str
    messaging_smtp_port: int
    messaging_smtp_user: str
    messaging_smtp_password: str
    messaging_smtp_from: str
    messaging_smtp_use_tls: bool


def get_settings() -> Settings:
    database_url = os.getenv("DGT_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError(
            "DGT_DATABASE_URL es obligatorio y debe apuntar a PostgreSQL."
        )

    return Settings(
        database_url=database_url,
        internal_api_key=os.getenv("DGT_INTERNAL_API_KEY", ""),
        public_base_url=os.getenv("DGT_PUBLIC_BASE_URL", "https://tramites.gestinem.es").rstrip("/"),
        token_ttl_hours=max(1, int(os.getenv("DGT_TOKEN_TTL_HOURS", "168"))),
        storage_dir=os.getenv("DGT_STORAGE_DIR", "./dgt_private_storage"),
        signrequest_token=os.getenv("SIGNREQUEST_TOKEN", ""),
        signrequest_from_email=os.getenv("SIGNREQUEST_FROM_EMAIL", ""),
        signrequest_gestor_email=os.getenv("SIGNREQUEST_GESTOR_EMAIL", ""),
        signrequest_gestor_telefono=os.getenv("SIGNREQUEST_GESTOR_TELEFONO", ""),
        signrequest_base_url=os.getenv("SIGNREQUEST_BASE_URL", "https://signrequest.com/api/v1").rstrip("/"),
        dataprius_api_key=os.getenv("DATAPRIUS_API_KEY", ""),
        dataprius_api_secret=os.getenv("DATAPRIUS_API_SECRET", ""),
        dataprius_base_url=os.getenv("DATAPRIUS_BASE_URL", "https://api.v2.dataprius.com").rstrip("/"),
        dataprius_base_path=os.getenv("DATAPRIUS_BASE_PATH", "FOLDERS/Gest2A3Eco/Tramites DGT").rstrip("/"),
        messaging_public_base_url=os.getenv(
            "MESSAGING_PUBLIC_BASE_URL",
            os.getenv("DGT_PUBLIC_BASE_URL", "https://tramites.gestinem.es"),
        ).rstrip("/"),
        messaging_storage_dir=os.getenv("MESSAGING_STORAGE_DIR", "./messaging_private_storage"),
        messaging_azure_connection_string=os.getenv("MESSAGING_AZURE_CONNECTION_STRING", ""),
        messaging_azure_container=os.getenv("MESSAGING_AZURE_CONTAINER", "mensajeria-temporal"),
        messaging_attachment_days=max(15, int(os.getenv("MESSAGING_ATTACHMENT_DAYS", "30"))),
        messaging_graph_tenant_id=os.getenv("MESSAGING_GRAPH_TENANT_ID", ""),
        messaging_graph_client_id=os.getenv("MESSAGING_GRAPH_CLIENT_ID", ""),
        messaging_graph_client_secret=os.getenv("MESSAGING_GRAPH_CLIENT_SECRET", ""),
        messaging_graph_from=os.getenv("MESSAGING_GRAPH_FROM", ""),
        messaging_graph_invitation_from=os.getenv("MESSAGING_GRAPH_INVITATION_FROM", ""),
        messaging_staff_tenant_id=os.getenv(
            "MESSAGING_STAFF_TENANT_ID", os.getenv("MESSAGING_GRAPH_TENANT_ID", ""),
        ),
        messaging_staff_client_id=os.getenv(
            "MESSAGING_STAFF_CLIENT_ID", os.getenv("MESSAGING_GRAPH_CLIENT_ID", ""),
        ),
        messaging_staff_client_secret=os.getenv(
            "MESSAGING_STAFF_CLIENT_SECRET", os.getenv("MESSAGING_GRAPH_CLIENT_SECRET", ""),
        ),
        messaging_staff_admin_emails=os.getenv(
            "MESSAGING_STAFF_ADMIN_EMAILS", "jjdominguez@gestinem.es",
        ),
        messaging_staff_allowed_domain=os.getenv(
            "MESSAGING_STAFF_ALLOWED_DOMAIN", "gestinem.es",
        ).strip().lower(),
        messaging_sync_token=os.getenv("MESSAGING_SYNC_TOKEN", ""),
        messaging_vapid_public_key=os.getenv("MESSAGING_VAPID_PUBLIC_KEY", ""),
        messaging_vapid_private_key=os.getenv("MESSAGING_VAPID_PRIVATE_KEY", ""),
        messaging_vapid_subject=os.getenv(
            "MESSAGING_VAPID_SUBJECT", "mailto:oficina@gestinem.es",
        ),
        messaging_smtp_host=os.getenv("MESSAGING_SMTP_HOST", ""),
        messaging_smtp_port=int(os.getenv("MESSAGING_SMTP_PORT", "587")),
        messaging_smtp_user=os.getenv("MESSAGING_SMTP_USER", ""),
        messaging_smtp_password=os.getenv("MESSAGING_SMTP_PASSWORD", ""),
        messaging_smtp_from=os.getenv("MESSAGING_SMTP_FROM", ""),
        messaging_smtp_use_tls=os.getenv("MESSAGING_SMTP_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "si"},
    )
