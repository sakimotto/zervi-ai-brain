import base64

import httpx
import pytest

from app import attachments


class FakeResponse:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=None, response=self
            )


@pytest.fixture(autouse=True)
def reset_import_limits(monkeypatch):
    """Keep attachment size limits at production values for most tests."""
    pass


class TestProcessSingleAttachment:
    async def test_uses_extracted_text_when_provided(self):
        att = {
            "id": 1,
            "name": "notes.txt",
            "mimetype": "text/plain",
            "access_url": "http://example.com/nope",
            "extracted_text": "hello world",
        }
        result = await attachments._process_single_attachment(att)
        assert result["text"] == "hello world"
        assert result["error"] is None

    async def test_downloads_and_decodes_text_file(self, monkeypatch):
        async def fake_get(self, url, **kwargs):
            return FakeResponse(b"file contents")

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

        att = {
            "id": 2,
            "name": "data.csv",
            "mimetype": "text/csv",
            "access_url": "http://example.com/data.csv",
        }
        result = await attachments._process_single_attachment(att)
        assert result["text"] == "file contents"
        assert result["error"] is None

    async def test_extracts_text_from_pdf(self, monkeypatch):
        # Minimal valid PDF header. pypdf will parse but extract no text;
        # we monkeypatch PdfReader to return a fake page.
        async def fake_get(self, url, **kwargs):
            return FakeResponse(b"%PDF-1.4 fake pdf bytes")

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

        class FakePage:
            def extract_text(self):
                return "PDF text"

        class FakeReader:
            pages = [FakePage()]

        monkeypatch.setattr(
            attachments,
            "_extract_text_from_pdf",
            lambda data: "PDF text",
        )

        att = {
            "id": 3,
            "name": "doc.pdf",
            "mimetype": "application/pdf",
            "access_url": "http://example.com/doc.pdf",
        }
        result = await attachments._process_single_attachment(att)
        assert result["text"] == "PDF text"

    async def test_image_gets_data_url(self, monkeypatch):
        async def fake_get(self, url, **kwargs):
            return FakeResponse(b"\x89PNG\r\n\x1a\n")

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

        att = {
            "id": 4,
            "name": "pic.png",
            "mimetype": "image/png",
            "access_url": "http://example.com/pic.png",
        }
        result = await attachments._process_single_attachment(att)
        assert result["image_data_url"].startswith("data:image/png;base64,")
        encoded = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode("ascii")
        assert result["image_data_url"] == f"data:image/png;base64,{encoded}"

    async def test_unsupported_mimetype(self, monkeypatch):
        async def fake_get(self, url, **kwargs):
            return FakeResponse(b"data")

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

        att = {
            "id": 5,
            "name": "file.zip",
            "mimetype": "application/zip",
            "access_url": "http://example.com/file.zip",
        }
        result = await attachments._process_single_attachment(att)
        assert result["error"] == "Unsupported attachment type: application/zip"

    async def test_download_failure(self, monkeypatch):
        async def fake_get(self, url, **kwargs):
            raise httpx.ConnectError("connection failed")

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

        att = {
            "id": 6,
            "name": "remote.txt",
            "mimetype": "text/plain",
            "access_url": "http://example.com/remote.txt",
        }
        result = await attachments._process_single_attachment(att)
        assert result["error"] == "Could not download attachment"

    async def test_size_limit(self, monkeypatch):
        monkeypatch.setattr(attachments, "_MAX_ATTACHMENT_BYTES", 5)

        async def fake_get(self, url, **kwargs):
            return FakeResponse(b"1234567890")

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

        att = {
            "id": 7,
            "name": "big.txt",
            "mimetype": "text/plain",
            "access_url": "http://example.com/big.txt",
        }
        result = await attachments._process_single_attachment(att)
        assert "exceeds size limit" in (result["error"] or "")
        assert "5 bytes" in (result["error"] or "")


class TestBuildUserMessageWithAttachments:
    def test_text_only(self):
        msg = attachments.build_user_message_with_attachments("hello", [])
        assert msg == {"role": "user", "content": "hello"}

    def test_with_text_attachment(self):
        processed = [
            {
                "id": 1,
                "name": "notes.txt",
                "mimetype": "text/plain",
                "text": "attachment text",
                "image_data_url": None,
                "error": None,
            }
        ]
        msg = attachments.build_user_message_with_attachments("hello", processed)
        assert msg["role"] == "user"
        assert "hello" in msg["content"]
        assert "attachment text" in msg["content"]

    def test_with_image_attachment(self):
        processed = [
            {
                "id": 2,
                "name": "pic.png",
                "mimetype": "image/png",
                "text": None,
                "image_data_url": "data:image/png;base64,abc",
                "error": None,
            }
        ]
        msg = attachments.build_user_message_with_attachments("hello", processed)
        assert msg["role"] == "user"
        assert isinstance(msg["content"], list)
        assert msg["content"][0]["type"] == "text"
        assert msg["content"][1]["type"] == "image_url"
        assert msg["content"][1]["image_url"]["url"] == "data:image/png;base64,abc"


class TestBuildAttachmentContext:
    async def test_empty_attachments(self):
        assert await attachments.build_attachment_context([]) is None

    async def test_includes_extracted_text(self):
        context = await attachments.build_attachment_context(
            [
                {
                    "id": 1,
                    "name": "notes.txt",
                    "mimetype": "text/plain",
                    "access_url": "http://x/nope",
                    "extracted_text": "line one\nline two",
                }
            ]
        )
        assert "notes.txt" in context
        assert "line one" in context

    async def test_includes_image_placeholder(self, monkeypatch):
        async def fake_get(self, url, **kwargs):
            return FakeResponse(b"\x89PNG")

        monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

        context = await attachments.build_attachment_context(
            [
                {
                    "id": 2,
                    "name": "pic.png",
                    "mimetype": "image/png",
                    "access_url": "http://x/pic.png",
                }
            ]
        )
        assert "pic.png" in context
        assert "will be provided to the vision model" in context


class TestAttachmentSchema:
    def test_accepts_odoo_payload_with_attachment_id_and_access_token(self):
        from app import schemas

        payload = {
            "message": "What is in this file?",
            "user_id": 1,
            "attachments": [
                {
                    "attachment_id": 42,
                    "name": "report.pdf",
                    "mimetype": "application/pdf",
                    "size": 1234,
                    "access_url": "https://example.com/web/content/42/token",
                    "access_token": "secret-token",
                    "extracted_text": None,
                }
            ],
        }
        req = schemas.ChatRequest(**payload)
        assert len(req.attachments) == 1
        att = req.attachments[0]
        assert att.id == 42
        assert att.access_token == "secret-token"

    def test_accepts_canonical_id_field(self):
        from app import schemas

        payload = {
            "message": "What is in this file?",
            "user_id": 1,
            "attachments": [
                {
                    "id": 7,
                    "name": "notes.txt",
                    "mimetype": "text/plain",
                    "access_url": "https://example.com/7",
                }
            ],
        }
        req = schemas.ChatRequest(**payload)
        assert req.attachments[0].id == 7


class TestBuildLlmMessagesWithAttachments:
    async def test_build_llm_messages_does_not_shadow_attachments_module(
        self, monkeypatch
    ):
        """Regression test: the attachments parameter must not shadow the module."""
        from app.main import _build_llm_messages

        async def fake_download(url, timeout=30.0):
            return b"file text content"

        monkeypatch.setattr("app.attachments._download_bytes", fake_download)

        attachment_dicts = [
            {
                "id": 1,
                "name": "notes.txt",
                "mimetype": "text/plain",
                "size": 100,
                "access_url": "https://example.com/notes.txt",
            }
        ]

        messages = await _build_llm_messages(
            system_prompt="You are Saki.",
            skill_schemas=[],
            context={},
            recent_messages=[],
            relevant_snippets=[],
            user_message="What is in this file?",
            attachment_dicts=attachment_dicts,
        )

        # Should include system prompt, attachment context, and user message.
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are Saki."
        assert any("notes.txt" in msg.get("content", "") for msg in messages)
        assert messages[-1]["role"] == "user"
        assert "file text content" in messages[-1]["content"]
