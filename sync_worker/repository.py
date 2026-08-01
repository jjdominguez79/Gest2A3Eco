from __future__ import annotations

import json
import re
from datetime import datetime

import psycopg
from psycopg.rows import dict_row


class ComunicacionesRepository:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def sync_messages(self, mailbox: str, messages: list[dict], delta_link: str) -> tuple[int, int]:
        inserted = duplicates = 0
        with psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            with conn.transaction():
                # El delta se obtiene antes de llamar a este metodo. Este bloqueo
                # evita que dos instancias escriban simultaneamente el mismo buzon.
                conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"mail-sync:{mailbox}",))
                for raw in messages:
                    data = self._normalize(raw, mailbox)
                    suggestion = self._find_company(conn, data["remitente"])
                    cursor = conn.execute(
                        """
                        INSERT INTO comunicaciones_sin_asignar
                          (graph_message_id,mailbox,remitente,asunto,fecha,cuerpo_html,
                           payload_json,sugerencia_codigo_empresa,sugerencia_nombre,
                           responsable_usuario_id,responsable_nombre,created_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,NULL,%s)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            data["graph_message_id"], mailbox, data["remitente"],
                            data["asunto"], data["fecha"], data["cuerpo_html"],
                            json.dumps(data, ensure_ascii=False),
                            (suggestion or {}).get("codigo"),
                            (suggestion or {}).get("nombre"),
                            datetime.now().astimezone().isoformat(timespec="seconds"),
                        ),
                    )
                    if cursor.rowcount:
                        inserted += 1
                    else:
                        duplicates += 1
                conn.execute(
                    """
                    INSERT INTO comunicaciones_sync
                      (mailbox,delta_link,ultima_sincronizacion,ultimo_error)
                    VALUES (%s,%s,%s,NULL)
                    ON CONFLICT(mailbox) DO UPDATE SET
                      delta_link=excluded.delta_link,
                      ultima_sincronizacion=excluded.ultima_sincronizacion,
                      ultimo_error=NULL
                    """,
                    (
                        mailbox,
                        delta_link,
                        datetime.now().astimezone().isoformat(timespec="seconds"),
                    ),
                )
        return inserted, duplicates

    def get_delta(self, mailbox: str) -> str:
        with psycopg.connect(self._dsn, row_factory=dict_row) as conn:
            row = conn.execute(
                "SELECT delta_link FROM comunicaciones_sync WHERE mailbox=%s",
                (mailbox,),
            ).fetchone()
            return str((row or {}).get("delta_link") or "")

    def record_error(self, mailbox: str, error: str) -> None:
        try:
            with psycopg.connect(self._dsn) as conn:
                conn.execute(
                    """
                    INSERT INTO comunicaciones_sync
                      (mailbox,delta_link,ultima_sincronizacion,ultimo_error)
                    VALUES (%s,'',%s,%s)
                    ON CONFLICT(mailbox) DO UPDATE SET
                      ultima_sincronizacion=excluded.ultima_sincronizacion,
                      ultimo_error=excluded.ultimo_error
                    """,
                    (
                        mailbox,
                        datetime.now().astimezone().isoformat(timespec="seconds"),
                        error[:1000],
                    ),
                )
        except Exception:
            pass

    @staticmethod
    def _find_company(conn, email: str) -> dict | None:
        value = str(email or "").strip().lower()
        if not value:
            return None
        rows = conn.execute(
            """
            SELECT e.codigo,e.ejercicio,e.nombre,e.responsable,e.email
            FROM empresas e
            JOIN (
              SELECT codigo,MAX(ejercicio) ejercicio FROM empresas GROUP BY codigo
            ) u ON u.codigo=e.codigo AND u.ejercicio=e.ejercicio
            UNION
            SELECT e.codigo,e.ejercicio,e.nombre,e.responsable,t.email
            FROM terceros t
            JOIN terceros_empresas te ON te.tercero_id=t.id
            JOIN empresas e ON e.codigo=te.codigo_empresa AND e.ejercicio=te.ejercicio
            """
        ).fetchall()
        matches = {}
        for row in rows:
            emails = {
                part.strip().lower()
                for part in re.split(r"[,;]", str(row.get("email") or ""))
                if part.strip()
            }
            if value in emails:
                matches[row["codigo"]] = row
        return next(iter(matches.values())) if len(matches) == 1 else None

    @staticmethod
    def _normalize(raw: dict, mailbox: str) -> dict:
        def address(value: dict | None) -> str:
            return str(((value or {}).get("emailAddress") or {}).get("address") or "").strip()

        return {
            "graph_message_id": str(raw.get("id") or ""),
            "graph_conversation_id": str(raw.get("conversationId") or ""),
            "internet_message_id": str(raw.get("internetMessageId") or ""),
            "mailbox": mailbox,
            "remitente": address(raw.get("from")),
            "destinatarios": [address(item) for item in raw.get("toRecipients") or [] if address(item)],
            "cc": [address(item) for item in raw.get("ccRecipients") or [] if address(item)],
            "asunto": str(raw.get("subject") or "(Sin asunto)"),
            "cuerpo_html": str((raw.get("body") or {}).get("content") or ""),
            "fecha": str(raw.get("receivedDateTime") or ""),
            "tiene_adjuntos": bool(raw.get("hasAttachments")),
            "leido": bool(raw.get("isRead")),
        }
