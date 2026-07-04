import pytest

from app.main import _parse_reply, _parse_skill_request, _parse_suggestion


class TestParseSkillRequest:
    def test_valid_skill_request(self):
        text = '{"skill": "locate_stock", "params": {"product_id": 123, "product_name": "Neoprene Black"}}'
        result = _parse_skill_request(text)
        assert result == {
            "skill": "locate_stock",
            "params": {"product_id": 123, "product_name": "Neoprene Black"},
        }

    def test_markdown_fences(self):
        text = "```json\n{\"skill\": \"locate_stock\", \"params\": {\"product_id\": 456}}\n```"
        result = _parse_skill_request(text)
        assert result == {"skill": "locate_stock", "params": {"product_id": 456}}

    def test_json_inside_explanatory_text(self):
        text = (
            "I will open the stock view for you now. "
            '{"skill": "locate_stock", "params": {"product_name": "Foam Grey"}}'
        )
        result = _parse_skill_request(text)
        assert result == {"skill": "locate_stock", "params": {"product_name": "Foam Grey"}}

    def test_missing_skill_returns_none(self):
        text = '{"params": {"product_id": 123}}'
        assert _parse_skill_request(text) is None

    def test_tool_request_returns_none(self):
        text = '{"tool": "confirm_sales_order", "params": {"res_id": 1}}'
        assert _parse_skill_request(text) is None

    def test_plain_text_returns_none(self):
        assert _parse_skill_request("I am just chatting") is None


class TestParseReply:
    def test_plain_reply(self):
        assert _parse_reply("Hello!") == {"reply": "Hello!"}

    def test_skill_request_priority(self):
        text = '{"skill": "locate_stock", "params": {"product_id": 123}}'
        result = _parse_reply(text)
        assert "skill_request" in result
        assert result["skill_request"]["skill"] == "locate_stock"
        assert "tool_request" not in result
        assert "reply" not in result

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
