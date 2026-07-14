import os
import re
import socket
import subprocess
import sys
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.agent import Agent
from app.mcp_client import (
    MCPConfigError,
    MCPManager,
    build_tool_name,
    expand_environment_map,
    format_mcp_result,
    normalize_tool_input_schema,
    normalize_server_configs,
    redact_text,
)


STDIO_SERVER_CODE = """from mcp.server.fastmcp import FastMCP
import os
import time
mcp = FastMCP('QuickModelTest')
secret = os.environ.get('MCP_TEST_SECRET', '')

def reveal(value: str = secret) -> str:
    return secret
reveal.__doc__ = 'configured secret: ' + secret
mcp.tool()(reveal)

@mcp.tool()
def echo(text: str) -> str:
    return 'echo:' + text

@mcp.tool()
def process_id() -> int:
    return os.getpid()

@mcp.tool()
def path_present() -> bool:
    return bool(os.environ.get('PATH'))

@mcp.tool()
def slow() -> str:
    time.sleep(5)
    return 'too late'

mcp.run(transport='stdio')
"""


def stdio_config(**overrides):
    config = {
        "id": "stdio-test",
        "name": "test server",
        "enabled": True,
        "transport": "stdio",
        "trusted": True,
        "connect_timeout": 20,
        "call_timeout": 20,
        "stdio": {
            "command": sys.executable,
            "args": ["-c", STDIO_SERVER_CODE],
            "cwd": os.getcwd(),
            "env": {"MCP_TEST_SECRET": "mcp-secret-value"},
        },
        "http": {"url": "", "headers": {}},
    }
    config.update(overrides)
    return config


def process_exists(pid):
    if sys.platform == "win32":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class ConfigTests(unittest.TestCase):
    def test_normalize_and_duplicate_names(self):
        normalized = normalize_server_configs([stdio_config(enabled=False)])
        self.assertEqual(normalized[0]["connect_timeout"], 20)
        self.assertEqual(normalized[0]["transport"], "stdio")
        with self.assertRaises(MCPConfigError):
            normalize_server_configs([stdio_config(id="a"), stdio_config(id="b", name="TEST SERVER")])

    def test_environment_expansion_and_redaction(self):
        with patch.dict(os.environ, {"MCP_TOKEN": "token-123456"}, clear=False):
            expanded, secrets = expand_environment_map({"Authorization": "Bearer ${MCP_TOKEN}"})
        self.assertEqual(expanded["Authorization"], "Bearer token-123456")
        self.assertNotIn("token-123456", redact_text("server echoed token-123456", secrets))
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MCPConfigError):
                expand_environment_map({"X": "${MISSING_TOKEN}"})

    def test_tool_names_are_valid_bounded_and_collision_safe(self):
        used = set()
        first = build_tool_name("server name", "tool/name", used, "one")
        second = build_tool_name("server name", "tool name", used, "two")
        long_name = build_tool_name("s" * 80, "t" * 80, used, "long")
        self.assertRegex(first, r"^[A-Za-z0-9_-]+$")
        self.assertNotEqual(first, second)
        self.assertLessEqual(len(long_name), 64)

    def test_input_schema_is_object_and_recursively_redacted(self):
        normalized = normalize_tool_input_schema(
            {
                "type": "object",
                "properties": {"token": {"type": "string", "default": "token-123456"}},
            },
            {"token-123456"},
        )
        self.assertEqual(normalized["properties"]["token"]["default"], "***")
        self.assertEqual(
            normalize_tool_input_schema({"type": "string"}, set()),
            {"type": "object", "properties": {}},
        )

    def test_result_formatting_and_truncation(self):
        result = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="abcdef")],
            structuredContent={"ok": True},
            isError=False,
        )
        rendered = format_mcp_result(result, max_chars=5)
        self.assertIn("结果已截断", rendered)


class ManagerIntegrationTests(unittest.TestCase):
    def test_disabled_server_is_not_started_or_exposed(self):
        manager = MCPManager([stdio_config(enabled=False)])
        try:
            self.assertEqual(manager.get_tool_schemas(), [])
            self.assertFalse(manager.get_statuses()[0]["enabled"])
            self.assertEqual(manager._workers, {})
        finally:
            manager.shutdown()

    def test_stdio_discovery_filter_redaction_call_and_cleanup(self):
        config = stdio_config(
            tool_policy="allowlist",
            enabled_tools=["reveal", "process_id", "path_present"],
        )
        manager = MCPManager([config])
        pid = None
        try:
            schemas = manager.get_tool_schemas()
            names = {item["function"]["name"]: item["function"] for item in schemas}
            self.assertEqual(len(names), 3)
            descriptions = "\n".join(item["description"] for item in names.values())
            self.assertNotIn("mcp-secret-value", descriptions)
            self.assertNotIn("mcp-secret-value", str(schemas))

            reveal_name = next(name for name in names if name.endswith("__reveal"))
            reveal_result = manager.call_tool(reveal_name, {})
            self.assertNotIn("mcp-secret-value", reveal_result)
            self.assertIn("***", reveal_result)

            path_name = next(name for name in names if name.endswith("__path_present"))
            self.assertIn("true", manager.call_tool(path_name, {}).lower())

            pid_name = next(name for name in names if name.endswith("__process_id"))
            pid_result = manager.call_tool(pid_name, {})
            pid = int(re.search(r"\d+", pid_result).group(0))
            self.assertTrue(process_exists(pid))

            manager.apply_config([])
            deadline = time.time() + 5
            while process_exists(pid) and time.time() < deadline:
                time.sleep(0.1)
            self.assertFalse(process_exists(pid))
        finally:
            manager.shutdown()
        self.assertFalse(manager._thread.is_alive())

    def test_tool_call_timeout_is_reported(self):
        manager = MCPManager([stdio_config(
            call_timeout=1,
            tool_policy="allowlist",
            enabled_tools=["slow"],
        )])
        try:
            schema = manager.get_tool_schemas()[0]
            started = time.monotonic()
            result = manager.call_tool(schema["function"]["name"], {})
            self.assertLess(time.monotonic() - started, 4)
            self.assertIn("MCP 调用失败", result)
        finally:
            manager.shutdown()

    def test_streamable_http_discovery_and_call(self):
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        code = f"""from mcp.server.fastmcp import Context, FastMCP
mcp = FastMCP('QuickModelHttpTest', host='127.0.0.1', port={port}, stateless_http=True)
@mcp.tool()
def add(a: int, b: int) -> int:
    return a + b
@mcp.tool()
def header_seen(ctx: Context) -> str:
    request = ctx.request_context.request
    return 'header-ok' if request and request.headers.get('x-test-token') == 'header-secret-value' else 'header-missing'
mcp.run(transport='streamable-http')
"""
        process = subprocess.Popen(
            [sys.executable, "-c", code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        manager = None
        try:
            deadline = time.time() + 15
            while time.time() < deadline:
                sock = socket.socket()
                try:
                    sock.settimeout(0.2)
                    sock.connect(("127.0.0.1", port))
                    break
                except OSError:
                    time.sleep(0.1)
                finally:
                    sock.close()
            else:
                self.fail("HTTP MCP test server did not start")

            with patch.dict(os.environ, {"MCP_HTTP_TOKEN": "header-secret-value"}, clear=False):
                manager = MCPManager([{
                    "id": "http-test",
                    "name": "http test",
                    "enabled": True,
                    "transport": "http",
                    "trusted": True,
                    "http": {
                        "url": f"http://127.0.0.1:{port}/mcp",
                        "headers": {"X-Test-Token": "${MCP_HTTP_TOKEN}"},
                    },
                }])
                schemas = manager.get_tool_schemas()
                self.assertEqual(len(schemas), 2)
                names = {item["function"]["name"]: item for item in schemas}
                add_name = next(name for name in names if name.endswith("__add"))
                header_name = next(name for name in names if name.endswith("__header_seen"))
                self.assertIn("7", manager.call_tool(add_name, {"a": 2, "b": 5}))
                self.assertIn("header-ok", manager.call_tool(header_name, {}))
                self.assertEqual(manager.get_statuses()[0]["state"], "connected")
        finally:
            if manager:
                manager.shutdown()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


class _FakeMCP:
    def __init__(self, trusted):
        self.trusted = trusted
        self.calls = []

    def is_mcp_tool(self, name):
        return name.startswith("mcp__")

    def get_call_info(self, name):
        return {"server": "demo", "tool": "write", "trusted": self.trusted}

    def call_tool(self, name, args):
        self.calls.append((name, args))
        return "called"


class AgentRoutingTests(unittest.TestCase):
    def _agent(self, trusted):
        agent = object.__new__(Agent)
        agent.mcp_manager = _FakeMCP(trusted)
        agent.command_safety = "confirm"
        agent._stop_flag = threading.Event()
        agent._tool_handlers = {}
        agent.search_config = {}
        agent.vision_config = {}
        agent.command_timeout = 30
        agent.project_path = ""
        agent._rounds_without_todo = 0
        agent._todo = SimpleNamespace(has_open_items=lambda: False)
        return agent

    def test_untrusted_mcp_requires_confirmation(self):
        agent = self._agent(False)
        confirmations = []
        results = []
        callback = SimpleNamespace(
            on_tool_start=lambda *_: None,
            on_tool_result=lambda *args: results.append(args),
            on_confirm=lambda name, args: confirmations.append((name, args)) or False,
            on_todo_update=None,
        )
        messages = []
        agent._execute_tools([{
            "id": "1", "function": {"name": "mcp__demo__write", "arguments": '{"path":"x"}'},
        }], messages, callback, 0, 5, None)
        self.assertEqual(len(confirmations), 1)
        self.assertEqual(agent.mcp_manager.calls, [])
        self.assertIn("用户拒绝", messages[-1]["content"])

    def test_trusted_mcp_bypasses_confirmation(self):
        agent = self._agent(True)
        callback = SimpleNamespace(
            on_tool_start=lambda *_: None,
            on_tool_result=lambda *_: None,
            on_confirm=lambda *_: self.fail("trusted MCP should not confirm"),
            on_todo_update=None,
        )
        messages = []
        agent._execute_tools([{
            "id": "1", "function": {"name": "mcp__demo__write", "arguments": '{}'},
        }], messages, callback, 0, 5, None)
        self.assertEqual(len(agent.mcp_manager.calls), 1)
        self.assertEqual(messages[-1]["content"], "called")


if __name__ == "__main__":
    unittest.main()
