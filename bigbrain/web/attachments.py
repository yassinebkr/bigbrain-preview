"""Persistent chat attachments (memory phase).

The user's files used to live only in the browser: the WS `send()`
dropped them on the floor. Now every attachment is uploaded to
``data/attachments/`` (env ``BIGBRAIN_ATTACHMENTS_DIR``) and recorded in
persistent memory, so the agent can recall months later that the user
shared this file — the openclaw image-memory lesson, without re-uploading
anything to an LLM: recall works on the file NAME/type/context, not on
content (no vision claim, no hidden cost).
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict

from aiohttp import web

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10 MB


def attachments_dir() -> Path:
    directory = Path(os.environ.get("BIGBRAIN_ATTACHMENTS_DIR",
                                    "data/attachments"))
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _safe_name(name: str) -> str:
    """Strip paths and hostile characters from a client-supplied name."""
    base = os.path.basename(name or "file")
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)
    return base[:120] or "file"


def save_attachment(name: str, type_: str, data: bytes) -> Dict[str, Any]:
    attachment_id = f"att-{uuid.uuid4().hex[:12]}"
    safe = _safe_name(name)
    path = attachments_dir() / f"{attachment_id}__{safe}"
    path.write_bytes(data)
    return {
        "id": attachment_id,
        "name": safe,
        "type": type_ or "application/octet-stream",
        "size": len(data),
        "path": str(path),
    }


def read_attachment(attachment_id: str) -> Path | None:
    """Resolve an attachment id to its stored file (no traversal)."""
    if not re.fullmatch(r"att-[a-f0-9]{12}", attachment_id or ""):
        return None
    for path in attachments_dir().glob(f"{attachment_id}__*"):
        if path.is_file():
            return path
    return None


async def _handle_upload(request: web.Request) -> web.Response:
    """POST /api/attachments (multipart) → {id, name, type, size, path}."""
    reader = await request.multipart()
    field = None
    while True:
        field = await reader.next()
        if field is None:
            return web.json_response(
                {"error": "no file field"}, status=400)
        if field.name == "file":
            break

    data = bytearray()
    while True:
        chunk = await field.read_chunk(MAX_ATTACHMENT_BYTES)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > MAX_ATTACHMENT_BYTES:
            return web.json_response(
                {"error": f"attachment exceeds {MAX_ATTACHMENT_BYTES // (1024*1024)} MB"},
                status=413)

    record = save_attachment(field.filename, field.headers.get(
        "Content-Type", ""), bytes(data))
    return web.json_response(record)


async def _handle_download(request: web.Request) -> web.Response:
    """GET /api/attachments/{id} → the stored file."""
    path = read_attachment(request.match_info["attachment_id"])
    if path is None:
        return web.json_response({"error": "unknown attachment"}, status=404)
    return web.FileResponse(path)


def setup_attachment_routes(app: web.Application) -> None:
    app.router.add_post("/api/attachments", _handle_upload)
    app.router.add_get("/api/attachments/{attachment_id}", _handle_download)
