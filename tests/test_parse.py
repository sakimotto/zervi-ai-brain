import pytest

from app.main import _parse_reply, _parse_suggestion


class TestParseReply:
    def test_plain_reply(self):
        assert _parse_reply("Hello!") == {"reply": "Hello!"}

    def test_tool_request_json(self):
        text = '{"tool": "confirm_sales_order", "params": {"id": 42}}'
        assert _parse_reply(text) == {
            "tool_request": {"tool": "confirm_sales_order", "params": {"id": 42}}
        }

    def test_tool_request_in_markdown_fence(self):
        text = '```json\n{"tool": "confirm_sales_order", "params": {"id": 42}}\n```'
        assert _parse_reply(text) == {
            "tool_request": {"tool": "confirm_sales_order", "params": {"id": 42}}
        }

    def test_tool_request_with_explanation_text(self):
        text = (
            "I will confirm this order for you.\n"
            '```json\n{"tool": "confirm_sales_order", "params": {"id": 7}}\n```'
        )
        assert _parse_reply(text) == {
            "tool_request": {"tool": "confirm_sales_order", "params": {"id": 7}}
        }

    def test_invalid_json_treated_as_reply(self):
        text = "Here is the info: {not valid json"
        assert _parse_reply(text) == {"reply": text}


class TestParseSuggestion:
    def test_plain_suggestion(self):
        assert _parse_suggestion("Confirm the order") == {
            "suggestion": "Confirm the order",
            "tool_request": None,
        }

    def test_json_suggestion(self):
        text = '{"suggestion": "Confirm the order", "tool_request": {"tool": "confirm", "params": {}}}'
        assert _parse_suggestion(text) == {
            "suggestion": "Confirm the order",
            "tool_request": {"tool": "confirm", "params": {}},
        }

    def test_suggestion_in_markdown_fence(self):
        text = '```json\n{"suggestion": "Check stock"}\n```'
        assert _parse_suggestion(text) == {
            "suggestion": "Check stock",
            "tool_request": None,
        }

    def test_non_dict_tool_request_is_ignored(self):
        text = '{"suggestion": "X", "tool_request": "bad"}'
        assert _parse_suggestion(text) == {
            "suggestion": "X",
            "tool_request": None,
        }

    def test_long_plain_suggestion_truncated(self):
        long_text = "x" * 1000
        result = _parse_suggestion(long_text)
        assert result["suggestion"] == "x" * 500
        assert result["tool_request"] is None
