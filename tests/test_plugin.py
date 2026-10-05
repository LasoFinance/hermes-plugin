"""Behavior tests for sign-in, approvals and the forwarder. Run: python3 -m unittest discover tests

They need no Hermes install and no network: the two Hermes modules the plugin imports are stubbed,
and every HTTP request goes to a fake that answers like laso.finance.
"""

import importlib.util
import io
import json
import sys
import types
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

PLUGIN_DIR = Path(__file__).resolve().parent.parent

# Stand-ins for the Hermes modules: get_secret reads ENV, save/remove write it.
ENV: dict[str, str] = {}
secret_scope = types.ModuleType("agent.secret_scope")
secret_scope.get_secret = lambda name, default=None: ENV.get(name, default)
hermes_config = types.ModuleType("hermes_cli.config")
hermes_config.save_env_value = lambda key, value: ENV.__setitem__(key, value)
hermes_config.remove_env_value = lambda key: ENV.pop(key, None) is not None
sys.modules.update(
    {
        "agent": types.ModuleType("agent"),
        "agent.secret_scope": secret_scope,
        "hermes_cli": types.ModuleType("hermes_cli"),
        "hermes_cli.config": hermes_config,
    }
)

spec = importlib.util.spec_from_file_location(
    "laso_finance", PLUGIN_DIR / "__init__.py", submodule_search_locations=[str(PLUGIN_DIR)]
)
plugin = importlib.util.module_from_spec(spec)
sys.modules["laso_finance"] = plugin
spec.loader.exec_module(plugin)
sign_in = sys.modules["laso_finance.sign_in"]
approvals = sys.modules["laso_finance.approvals"]
mcp_client = sys.modules["laso_finance.mcp_client"]


class FakeState:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


class FakeResponse(io.BytesIO):
    def __init__(self, body: dict, status: int = 200):
        super().__init__(json.dumps(body).encode())
        self.status = status


class FakeLaso:
    """Answers urlopen like laso.finance. `token_replies` are returned in order by /oauth/token."""

    def __init__(self, token_replies=(), mcp_status=200):
        self.token_replies = list(token_replies)
        self.mcp_status = mcp_status
        self.paths = []

    def urlopen(self, request, timeout=None):
        path = request.full_url.removeprefix("https://laso.finance")
        self.paths.append(path)
        if path == "/oauth/device_authorization":
            return FakeResponse(
                {
                    "device_code": "BCDFGHJK.secret",
                    "user_code": "BCDF-GHJK",
                    "verification_uri_complete": "https://laso.finance/oauth/device?user_code=BCDF-GHJK",
                    "expires_in": 600,
                    "interval": 5,
                }
            )
        if path == "/oauth/token":
            status, body = self.token_replies.pop(0)
            if status != 200:
                raise urllib.error.HTTPError(request.full_url, status, "", {}, io.BytesIO(json.dumps(body).encode()))
            return FakeResponse(body)
        if path == "/mcp":
            if self.mcp_status != 200:
                raise urllib.error.HTTPError(request.full_url, self.mcp_status, "", {}, io.BytesIO(b"{}"))
            return FakeResponse({"result": {"content": [{"type": "text", "text": '{"balance": 12.5}'}]}})
        raise AssertionError(f"unexpected request to {path}")


class PluginTestCase(unittest.TestCase):
    def setUp(self):
        ENV.clear()
        sign_in._fresh_key = None
        self.ctx = types.SimpleNamespace(state=FakeState())
        sign_in.bind(self.ctx)
        self.clock = 1_000_000
        patcher = mock.patch.object(sign_in.time, "time", lambda: self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)

    def serve(self, laso: FakeLaso):
        patcher = mock.patch("urllib.request.urlopen", laso.urlopen)
        patcher.start()
        self.addCleanup(patcher.stop)
        return laso


class SignInTest(PluginTestCase):
    def test_first_call_returns_the_link_and_code(self):
        self.serve(FakeLaso())
        result = json.loads(sign_in.connect())
        self.assertEqual(result["error"], "laso_not_connected")
        self.assertIn("https://laso.finance/oauth/device?user_code=BCDF-GHJK", result["message_for_human"])
        self.assertIn("BCDF-GHJK", result["message_for_human"])

    def test_approval_saves_the_key_and_lets_the_call_through(self):
        self.serve(FakeLaso(token_replies=[(200, {"access_token": "lasoak_new"})]))
        sign_in.connect()
        self.clock += 10
        self.assertIsNone(sign_in.connect())
        self.assertEqual(ENV["LASO_API_KEY"], "lasoak_new")
        self.assertEqual(sign_in.current_key(), "lasoak_new")
        self.assertIsNone(self.ctx.state.get(sign_in.PENDING_STATE_KEY))

    def test_a_call_before_the_interval_does_not_poll(self):
        laso = self.serve(FakeLaso())
        sign_in.connect()
        self.clock += 2
        result = json.loads(sign_in.connect())
        self.assertEqual(result["error"], "laso_not_connected")
        self.assertNotIn("/oauth/token", laso.paths)

    def test_pending_and_slow_down_keep_the_same_code(self):
        self.serve(
            FakeLaso(token_replies=[(400, {"error": "authorization_pending"}), (400, {"error": "slow_down"})])
        )
        sign_in.connect()
        self.clock += 10
        self.assertIn("Still waiting", json.loads(sign_in.connect())["message_for_human"])
        self.clock += 10
        sign_in.connect()
        self.assertEqual(self.ctx.state.get(sign_in.PENDING_STATE_KEY)["interval"], 10)

    def test_a_declined_connection_says_so_and_does_not_restart(self):
        laso = self.serve(FakeLaso(token_replies=[(400, {"error": "access_denied"})]))
        sign_in.connect()
        self.clock += 10
        self.assertEqual(json.loads(sign_in.connect())["error"], "laso_connection_declined")
        self.assertEqual(laso.paths.count("/oauth/device_authorization"), 1)

    def test_an_expired_code_starts_over(self):
        laso = self.serve(FakeLaso())
        sign_in.connect()
        self.clock += 601
        sign_in.connect()
        self.assertEqual(laso.paths.count("/oauth/device_authorization"), 2)

    def test_a_key_in_env_skips_sign_in(self):
        laso = self.serve(FakeLaso())
        ENV["LASO_API_KEY"] = "lasoak_existing"
        self.assertIsNone(sign_in.connect())
        self.assertEqual(laso.paths, [])


class ForwarderTest(PluginTestCase):
    def test_a_connected_call_returns_the_tool_result(self):
        self.serve(FakeLaso())
        ENV["LASO_API_KEY"] = "lasoak_existing"
        self.assertEqual(json.loads(mcp_client.call_tool("get_account_balance", {})), {"balance": 12.5})

    def test_a_revoked_key_is_dropped_and_sign_in_restarts(self):
        self.serve(FakeLaso(mcp_status=401))
        ENV["LASO_API_KEY"] = "lasoak_revoked"
        result = json.loads(mcp_client.call_tool("get_account_balance", {}))
        self.assertEqual(result["error"], "laso_not_connected")
        self.assertNotIn("LASO_API_KEY", ENV)


class ApprovalsTest(PluginTestCase):
    def setUp(self):
        super().setUp()
        self.hook = approvals.make_hook({"laso_send_payment"})

    def test_money_moving_tools_ask_for_approval_with_the_details(self):
        ENV["LASO_API_KEY"] = "lasoak_existing"
        directive = self.hook(
            tool_name="laso_send_payment",
            args={"amount": 25, "recipient": "@alex", "note": "", "meta": {"nested": True}},
        )
        self.assertEqual(directive["action"], "approve")
        self.assertIn('amount=25, recipient="@alex"', directive["message"])
        self.assertNotIn("meta", directive["message"])

    def test_read_only_tools_run_without_asking(self):
        ENV["LASO_API_KEY"] = "lasoak_existing"
        self.assertIsNone(self.hook(tool_name="laso_get_account_balance", args={}))

    def test_nothing_to_approve_before_sign_in(self):
        self.assertIsNone(self.hook(tool_name="laso_send_payment", args={"amount": 25}))


class ManifestTest(unittest.TestCase):
    def test_every_tool_has_an_approval_flag(self):
        catalog = json.loads((PLUGIN_DIR / "tools.json").read_text())
        for tool in catalog["tools"]:
            self.assertIsInstance(tool["requires_approval"], bool, tool["name"])
        approved = {tool["name"] for tool in catalog["tools"] if tool["requires_approval"]}
        self.assertTrue({"laso_send_payment", "laso_withdraw", "laso_create_agent_api_key"} <= approved)
        self.assertNotIn("laso_get_account_balance", approved)


if __name__ == "__main__":
    unittest.main()
