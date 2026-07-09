"""Attachment download and text extraction for chat messages."""

import asyncio
import base64
import logging
from io import BytesIO
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Plain-text MIME types that the brain can decode directly.
_TEXT_MIME_PREFIXES = ("text/", "application/csv", "application/json")

# Maximum bytes to download for any attachment (10 MB).
_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

# Maximum characters to include from extracted text per attachment.
_MAX_TEXT_CHARS = 8_000


def _is_text_mimetype(mimetype: str) -> bool:
    return any(mimetype.lower().startswith(prefix) for prefix in _TEXT_MIME_PREFIXES)


def _truncate_text(text: str, limit: int = _MAX_TEXT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... [content truncated]"


class AttachmentTooLargeError(Exception):
    """Raised when an attachment exceeds the configured size limit."""


async def _download_bytes(url: str, timeout: float = 30.0) -> Optional[bytes]:
    """Download attachment bytes from an Odoo /web/content URL."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, follow_redirects=True, timeout=timeout)
            response.raise_for_status()
            if len(response.content) > _MAX_ATTACHMENT_BYTES:
                raise AttachmentTooLargeError(
                    f"Attachment exceeds size limit ({_MAX_ATTACHMENT_BYTES} bytes)"
                )
            return response.content
    except AttachmentTooLargeError:
        raise
    except Exception as exc:
        logger.warning("Failed to download attachment from %s: %s", url, exc)
        return None


def _extract_text_from_pdf(data: bytes) -> Optional[str]:
    """Extract text from a PDF using pypdf if available."""
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - library import
        logger.warning("pypdf not available for PDF extraction: %s", exc)
        return None

    try:
        reader = PdfReader(BytesIO(data))
        parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                parts.append(text)
        return "\n".join(parts) if parts else None
    except Exception as exc:
        logger.warning("Failed to extract text from PDF: %s", exc)
        return None


def _image_data_url(mimetype: str, data: bytes) -> str:
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mimetype};base64,{encoded}"


async def _process_single_attachment(attachment: Dict[str, Any]) -> Dict[str, Any]:
    """Return a processed attachment summary for prompt building."""
    name = attachment.get("name", "unnamed")
    mimetype = attachment.get("mimetype", "application/octet-stream")
    access_url = attachment.get("access_url") or attachment.get("url")
    extracted_text = attachment.get("extracted_text")

    result = {
        "id": attachment.get("id"),
        "name": name,
        "mimetype": mimetype,
        "size": attachment.get("size"),
        "text": None,
        "image_data_url": None,
        "error": None,
    }

    # If Odoo already extracted text, trust it.
    if extracted_text:
        result["text"] = _truncate_text(str(extracted_text))
        return result

    if not access_url:
        result["error"] = "No access URL provided"
        return result

    try:
        data = await _download_bytes(access_url)
    except AttachmentTooLargeError as exc:
        result["error"] = str(exc)
        return result
    if data is None:
        result["error"] = "Could not download attachment"
        return result

    if _is_text_mimetype(mimetype):
        try:
            result["text"] = _truncate_text(data.decode("utf-8", errors="replace"))
        except Exception as exc:
            result["error"] = f"Could not decode text file: {exc}"
        return result

    if mimetype.lower() == "application/pdf":
        text = _extract_text_from_pdf(data)
        if text:
            result["text"] = _truncate_text(text)
        else:
            result["error"] = "Could not extract text from PDF"
        return result

    if mimetype.startswith("image/"):
        result["image_data_url"] = _image_data_url(mimetype, data)
        return result

    result["error"] = f"Unsupported attachment type: {mimetype}"
    return result


async def process_attachments(
    attachments: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Process all attachments in parallel."""
    if not attachments:
        return []
    results = await asyncio.gather(
        *[_process_single_attachment(att) for att in attachments]
    )
    return list(results)


async def build_attachment_context(
    attachments: List[Dict[str, Any]],
) -> Optional[str]:
    """Build a system-style context string summarising the user's attachments."""
    processed = await process_attachments(attachments)
    if not processed:
        return None

    lines = ["The user has attached the following files:"]
    for idx, item in enumerate(processed, start=1):
        name = item.get("name", "unnamed")
        mimetype = item.get("mimetype", "unknown")
        lines.append(f"{idx}. {name} ({mimetype})")
        if item.get("text"):
            lines.append(f"Content for {name}:")
            lines.append("```")
            lines.append(item["text"])
            lines.append("```")
        elif item.get("image_data_url"):
            lines.append(f"[Image {name} will be provided to the vision model below]")
        elif item.get("error"):
            lines.append(f"[Error reading {name}: {item['error']}]")

    return "\n".join(lines)


def build_user_message_with_attachments(
    message: str,
    processed_attachments: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a user message for the LLM.

    If images are present, the content is a list of text and image_url blocks
    (OpenAI-compatible format). Otherwise a simple text string is returned.
    """
    images = [att for att in processed_attachments if att.get("image_data_url")]
    text_parts = [message]

    non_image_attachments = [att for att in processed_attachments if not att.get("image_data_url")]
    if non_image_attachments:
        text_parts.append("\n\nAttached files:")
        for att in non_image_attachments:
            if att.get("text"):
                text_parts.append(f"\n--- {att['name']} ---\n{att['text']}")
            elif att.get("error"):
                text_parts.append(f"\n--- {att['name']} ---\n[Could not read: {att['error']}]")

    content_text = "\n".join(text_parts)

    if not images:
        return {"role": "user", "content": content_text}

    content: List[Dict[str, Any]] = [{"type": "text", "text": content_text}]
    for att in images:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": att["image_data_url"]},
            }
        )
    return {"role": "user", "content": content}
