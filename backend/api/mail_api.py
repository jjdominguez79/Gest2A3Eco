from __future__ import annotations

import base64
import json
from urllib.parse import quote

import requests
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from backend.api.config import get_settings
from backend.api.messaging_mail import configured, default_sender, graph_headers, send_mail
from backend.api.security import require_workstation_or_internal


router = APIRouter(prefix="/api/v1/mail", tags=["mail"])
MAX_TOTAL_BYTES = 20 * 1024 * 1024
GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


def _addresses(raw: str, field: str) -> list[str]:
    try:
        values = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"{field} no es una lista valida") from exc
    if not isinstance(values, list):
        raise HTTPException(status_code=422, detail=f"{field} no es una lista valida")
    result = [str(value).strip() for value in values if str(value).strip()]
    if any("@" not in value or len(value) > 254 for value in result):
        raise HTTPException(status_code=422, detail=f"{field} contiene una direccion no valida")
    return result


async def _read_files(files: list[UploadFile], *, inline: bool = False) -> list[dict]:
    result = []
    for upload in files:
        content = await upload.read()
        result.append({
            "name": upload.filename or "adjunto",
            "content_type": upload.content_type or "application/octet-stream",
            "content": content,
            "content_id": "gestinem-logo" if inline else "",
        })
    return result


@router.post("/send", dependencies=[Depends(require_workstation_or_internal)])
async def send_backend_mail(
    to: str = Form(...), cc: str = Form("[]"), bcc: str = Form("[]"),
    subject: str = Form(...), html: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    inline_files: list[UploadFile] = File(default=[]),
):
    recipients = _addresses(to, "to")
    if not recipients:
        raise HTTPException(status_code=422, detail="Debes indicar al menos un destinatario")
    if not configured():
        raise HTTPException(status_code=503, detail="El correo no esta configurado en el backend")
    attachments = await _read_files(files)
    attachments.extend(await _read_files(inline_files, inline=True))
    if sum(len(item["content"]) for item in attachments) > MAX_TOTAL_BYTES:
        raise HTTPException(status_code=413, detail="Los adjuntos superan el limite de 20 MB")
    try:
        sent = send_mail(
            recipients, subject.strip(), html, cc=_addresses(cc, "cc"),
            bcc=_addresses(bcc, "bcc"), attachments=attachments,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not sent:
        raise HTTPException(status_code=503, detail="El backend no pudo enviar el correo")
    return {"sent": True, "sender": default_sender()}


def _graph_url(mailbox: str, message_id: str, suffix: str = "") -> str:
    return (
        f"{GRAPH_ROOT}/users/{quote(mailbox, safe='')}/messages/"
        f"{quote(message_id, safe='')}{suffix}"
    )


def _graph_request_error(response, operation: str) -> HTTPException:
    try:
        detail = response.json().get("error", {}).get("message")
    except Exception:
        detail = ""
    return HTTPException(
        status_code=502,
        detail=detail or f"Microsoft Graph no pudo {operation} (HTTP {response.status_code})",
    )


def _validate_mailbox(mailbox: str) -> str:
    configured_mailbox = default_sender()
    mailbox = str(mailbox or "").strip()
    if not configured_mailbox or mailbox.lower() != configured_mailbox.lower():
        raise HTTPException(status_code=403, detail="Buzon de Microsoft 365 no autorizado")
    return mailbox


def _add_reply_attachment(
    mailbox: str, draft_id: str, item: dict, headers: dict[str, str],
) -> None:
    content = item["content"]
    if len(content) <= 3 * 1024 * 1024:
        added = requests.post(
            _graph_url(mailbox, draft_id, "/attachments"),
            headers=headers,
            json={
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": item["name"],
                "contentType": item["content_type"],
                "contentBytes": base64.b64encode(content).decode("ascii"),
            },
            timeout=90,
        )
        if added.status_code not in (200, 201):
            raise _graph_request_error(added, f"adjuntar {item['name']}")
        return

    session = requests.post(
        _graph_url(mailbox, draft_id, "/attachments/createUploadSession"),
        headers=headers,
        json={"AttachmentItem": {
            "attachmentType": "file", "name": item["name"], "size": len(content),
        }},
        timeout=45,
    )
    if session.status_code not in (200, 201):
        raise _graph_request_error(session, f"preparar el adjunto {item['name']}")
    upload_url = str(session.json().get("uploadUrl") or "")
    if not upload_url:
        raise HTTPException(status_code=502, detail="Microsoft Graph no devolvio la sesion de carga")
    chunk_size = 10 * 320 * 1024
    for start in range(0, len(content), chunk_size):
        chunk = content[start:start + chunk_size]
        end = start + len(chunk) - 1
        uploaded = requests.put(
            upload_url,
            headers={
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end}/{len(content)}",
            },
            data=chunk, timeout=120,
        )
        if uploaded.status_code not in (200, 201, 202):
            raise _graph_request_error(uploaded, f"cargar el adjunto {item['name']}")


@router.get(
    "/attachments",
    dependencies=[Depends(require_workstation_or_internal)],
)
def list_backend_attachments(
    mailbox: str = Query(min_length=3), message_id: str = Query(min_length=1),
):
    mailbox = _validate_mailbox(mailbox)
    try:
        response = requests.get(
            _graph_url(
                mailbox, message_id,
                "/attachments?$select=id,name,size,contentType,isInline",
            ),
            headers=graph_headers(get_settings()), timeout=45,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if response.status_code != 200:
        raise _graph_request_error(response, "consultar los adjuntos")
    return [
        item for item in response.json().get("value", [])
        if item.get("@odata.type") == "#microsoft.graph.fileAttachment"
        and not item.get("isInline", False)
    ]


@router.get(
    "/attachment",
    dependencies=[Depends(require_workstation_or_internal)],
)
def download_backend_attachment(
    mailbox: str = Query(min_length=3), message_id: str = Query(min_length=1),
    attachment_id: str = Query(min_length=1),
):
    mailbox = _validate_mailbox(mailbox)
    try:
        response = requests.get(
            _graph_url(
                mailbox, message_id,
                f"/attachments/{quote(attachment_id, safe='')}",
            ),
            headers=graph_headers(get_settings()), timeout=60,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if response.status_code != 200:
        raise _graph_request_error(response, "descargar el adjunto")
    item = response.json()
    content = item.get("contentBytes")
    if item.get("@odata.type") != "#microsoft.graph.fileAttachment" or not content:
        raise HTTPException(status_code=422, detail="El adjunto no es un archivo descargable")
    return item


@router.post(
    "/reply",
    dependencies=[Depends(require_workstation_or_internal)],
)
async def reply_backend_mail(
    mailbox: str = Form(...), message_id: str = Form(...), html: str = Form(...),
    files: list[UploadFile] = File(default=[]),
):
    mailbox = _validate_mailbox(mailbox)
    attachments = await _read_files(files)
    if sum(len(item["content"]) for item in attachments) > MAX_TOTAL_BYTES:
        raise HTTPException(status_code=413, detail="Los adjuntos superan el limite de 20 MB")
    try:
        headers = graph_headers(get_settings())
        json_headers = {**headers, "Content-Type": "application/json"}
        created = requests.post(
            _graph_url(mailbox, message_id, "/createReply"),
            headers=json_headers, json={}, timeout=45,
        )
        if created.status_code not in (200, 201):
            raise _graph_request_error(created, "crear la respuesta")
        draft_id = str(created.json().get("id") or "")
        if not draft_id:
            raise HTTPException(status_code=502, detail="Microsoft Graph no devolvio el borrador")
        updated = requests.patch(
            _graph_url(mailbox, draft_id), headers=json_headers,
            json={"body": {"contentType": "HTML", "content": html}}, timeout=45,
        )
        if updated.status_code not in (200, 202):
            raise _graph_request_error(updated, "preparar la respuesta")
        for item in attachments:
            _add_reply_attachment(mailbox, draft_id, item, json_headers)
        sent = requests.post(
            _graph_url(mailbox, draft_id, "/send"),
            headers=json_headers, json={}, timeout=45,
        )
        if sent.status_code not in (202, 204):
            raise _graph_request_error(sent, "enviar la respuesta")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"sent": True, "sender": mailbox, "message_id": draft_id}
