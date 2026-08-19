from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from backend.api.messaging_mail import configured, default_sender, send_mail
from backend.api.security import require_workstation_or_internal


router = APIRouter(prefix="/api/v1/mail", tags=["mail"])
MAX_TOTAL_BYTES = 20 * 1024 * 1024


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
