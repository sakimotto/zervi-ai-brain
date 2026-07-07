import pytest

from app.main import _extract_json, _parse_reply, _validate_tool_request


class DummySkill:
    def __init__(self, schemas):
        self.tool_schemas_json = schemas


class DummyAgent:
    """Minimal stand-in for an AIAgent with skills."""

    def __init__(self, skill_schemas_list):
        self.skills = [DummySkill(schemas) for schemas in skill_schemas_list]


class TestValidateToolRequest:
    def test_search_records_allowed(self):
        agent = DummyAgent([[{"tool": "search_records"}]])
        request = {"tool": "search_records", "params": {"res_model": "account.account", "domain": []}}
        assert _validate_tool_request(request, agent) == {"tool": "search_records", "params": request["params"]}

    def test_get_coa_summary_allowed(self):
        agent = DummyAgent([[{"tool": "get_coa_summary"}]])
        request = {"tool": "get_coa_summary", "params": {"prefix": "113"}}
        assert _validate_tool_request(request, agent) == {"tool": "get_coa_summary", "params": {"prefix": "113"}}

    def test_get_inventory_valuation_setup_allowed(self):
        agent = DummyAgent([[{"tool": "get_inventory_valuation_setup"}]])
        request = {"tool": "get_inventory_valuation_setup", "params": {}}
        assert _validate_tool_request(request, agent) == {"tool": "get_inventory_valuation_setup", "params": {}}

    def test_unknown_tool_rejected(self):
        agent = DummyAgent([[{"tool": "search_records"}]])
        request = {"tool": "delete_everything", "params": {}}
        assert _validate_tool_request(request, agent) is None

    def test_missing_params_rejected(self):
        agent = DummyAgent([[{"tool": "search_records"}]])
        request = {"tool": "search_records"}
        assert _validate_tool_request(request, agent) is None


class TestExtractJson:
    def test_single_tool_object(self):
        text = '{"tool": "search_records", "params": {"res_model": "account.account", "domain": []}}'
        assert _extract_json(text) == {
            "tool": "search_records",
            "params": {"res_model": "account.account", "domain": []},
        }

    def test_multiple_tool_array(self):
        text = '[{"tool": "search_records", "params": {"a": 1}}, {"tool": "get_coa_summary", "params": {"b": 2}}]'
        assert _extract_json(text) == [
            {"tool": "search_records", "params": {"a": 1}},
            {"tool": "get_coa_summary", "params": {"b": 2}},
        ]

    def test_markdown_fenced_object(self):
        text = "```json\n{\"tool\": \"search_records\", \"params\": {}}\n```"
        assert _extract_json(text) == {"tool": "search_records", "params": {}}

    def test_plain_text_is_ignored(self):
        text = "Here is a list: [account 1, account 2] and a value {foo: bar}."
        assert _extract_json(text) is None

    def test_plain_dict_without_tool_keys_is_ignored(self):
        text = '{"summary": "hello", "count": 5}'
        assert _extract_json(text) is None

    def test_conversational_reply_with_brackets_ignored(self):
        text = "You can see [Receipts](action:stock.picking.type/1) and [Delivery Orders](action:stock.picking.type/2)."
        assert _extract_json(text) is None

    def test_truncated_object_falls_back_to_none(self):
        text = '{"tool": "search_records", "params": {"res_model": "account.account"'
        assert _extract_json(text) is None

    def test_object_embedded_in_prose(self):
        text = 'I will search now. {"tool": "search_records", "params": {"res_model": "account.account"}}'
        assert _extract_json(text) == {
            "tool": "search_records",
            "params": {"res_model": "account.account"},
        }


class TestParseReplyWithNewTools:
    def test_search_records_tool_request(self):
        text = '{"tool": "search_records", "params": {"res_model": "account.account", "domain": [["code", "=like", "113%"]]}}'
        assert _parse_reply(text) == {
            "tool_request": {
                "tool": "search_records",
                "params": {"res_model": "account.account", "domain": [["code", "=like", "113%"]]},
            },
            "multi_tool_requests": None,
        }

    def test_get_coa_summary_tool_request(self):
        text = '{"tool": "get_coa_summary", "params": {"prefix": "113"}}'
        assert _parse_reply(text) == {
            "tool_request": {"tool": "get_coa_summary", "params": {"prefix": "113"}},
            "multi_tool_requests": None,
        }

    def test_get_inventory_valuation_setup_tool_request(self):
        text = '{"tool": "get_inventory_valuation_setup", "params": {}}'
        assert _parse_reply(text) == {
            "tool_request": {"tool": "get_inventory_valuation_setup", "params": {}},
            "multi_tool_requests": None,
        }

    def test_plain_text_reply(self):
        text = "Hello Archie, how can I help you today?"
        assert _parse_reply(text) == {
            "reply": "Hello Archie, how can I help you today?",
            "tool_request": None,
            "multi_tool_requests": None,
        }

    def test_multiple_tool_requests(self):
        text = '[{"tool": "search_records", "params": {"a": 1}}, {"tool": "get_coa_summary", "params": {"b": 2}}]'
        assert _parse_reply(text) == {
            "tool_request": {"tool": "search_records", "params": {"a": 1}},
            "multi_tool_requests": [
                {"tool": "search_records", "params": {"a": 1}},
                {"tool": "get_coa_summary", "params": {"b": 2}},
            ],
        }

    def test_conversational_markdown_ignored(self):
        text = "See [this link](action:product.template/123) for details."
        assert _parse_reply(text) == {
            "reply": "See [this link](action:product.template/123) for details.",
            "tool_request": None,
            "multi_tool_requests": None,
        }

    def test_partial_json_does_not_break_plain_text(self):
        text = "I found {some partial json that is not valid."
        assert _parse_reply(text) == {
            "reply": "I found {some partial json that is not valid.",
            "tool_request": None,
            "multi_tool_requests": None,
        }
