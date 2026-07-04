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
    def test_skill_request_priority(self):
        text = '{"skill": "locate_stock", "params": {"product_id": 123}}'
        result = _parse_reply(text)
        assert "skill_request" in result
        assert result["skill_request"]["skill"] == "locate_stock"
        assert "tool_request" not in result
        assert "reply" not in result

    def test_tool_request(self):
        text = '{"tool": "confirm_sales_order", "params": {"res_id": 1, "confirmation_message": "Confirm?"}}'
        result = _parse_reply(text)
        assert result["tool_request"]["tool"] == "confirm_sales_order"

    def test_conversational_reply(self):
        text = "The sales order is still in draft."
        result = _parse_reply(text)
        assert result["reply"] == text


class TestParseSuggestion:
    def test_valid_suggestion(self):
        text = '{"suggestion": "Confirm this order", "tool_request": null}'
        result = _parse_suggestion(text)
        assert result["suggestion"] == "Confirm this order"
        assert result["tool_request"] is None

    def test_suggestion_with_tool(self):
        text = '{"suggestion": "Validate picking", "tool_request": {"tool": "validate_picking", "params": {"res_id": 7}}}'
        result = _parse_suggestion(text)
        assert result["suggestion"] == "Validate picking"
        assert result["tool_request"]["tool"] == "validate_picking"

    def test_plain_text(self):
        text = "Confirm this order"
        result = _parse_suggestion(text)
        assert result["suggestion"] == text
        assert result["tool_request"] is None
