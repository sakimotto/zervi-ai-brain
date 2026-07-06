import pytest

from app.main import _parse_reply, _validate_tool_request


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


class TestParseReplyWithNewTools:
    def test_search_records_tool_request(self):
        text = '{"tool": "search_records", "params": {"res_model": "account.account", "domain": [["code", "=like", "113%"]]}}'
        assert _parse_reply(text) == {
            "tool_request": {
                "tool": "search_records",
                "params": {"res_model": "account.account", "domain": [["code", "=like", "113%"]]},
            }
        }

    def test_get_coa_summary_tool_request(self):
        text = '{"tool": "get_coa_summary", "params": {"prefix": "113"}}'
        assert _parse_reply(text) == {
            "tool_request": {"tool": "get_coa_summary", "params": {"prefix": "113"}}
        }

    def test_get_inventory_valuation_setup_tool_request(self):
        text = '{"tool": "get_inventory_valuation_setup", "params": {}}'
        assert _parse_reply(text) == {
            "tool_request": {"tool": "get_inventory_valuation_setup", "params": {}}
        }
