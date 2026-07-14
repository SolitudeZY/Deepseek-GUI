# MCP Client Integration

## Scenario: Persistent MCP tools in the Agent loop

### 1. Scope / Trigger

Use this contract when adding or changing MCP transports, tool discovery, Agent routing,
settings bridges, secret handling, or frozen-package support. QuickModel supports MCP Tools
over stdio and Streamable HTTP. Resources, Prompts, Sampling, Elicitation, OAuth, and legacy
SSE are outside this contract.

### 2. Signatures

Backend manager:

```python
MCPManager(servers: list[dict])
MCPManager.get_tool_schemas() -> list[dict]
MCPManager.call_tool(generated_name: str, arguments: dict) -> str
MCPManager.test_server(raw_config: dict) -> dict
MCPManager.get_statuses() -> list[dict]
MCPManager.reconnect(server_id: str) -> dict
MCPManager.apply_config(raw_servers: list[dict]) -> list[dict]
MCPManager.shutdown() -> None
```

WebView bridge:

```python
API.test_mcp_server(config: dict) -> dict
API.get_mcp_statuses() -> list[dict]
API.reconnect_mcp_server(server_id: str) -> dict
API.save_config(config: dict) -> {"ok": bool, "error"?: str}
```

### 3. Contracts

- Each server has a stable `id`, unique case-insensitive `name`, `enabled`, `transport`,
  `trusted`, `connect_timeout`, `call_timeout`, `tool_policy`, and `enabled_tools`.
- `transport` is `stdio` or `http`. HTTP means Streamable HTTP.
- `${ENV_VAR}` expansion is allowed in stdio env values and HTTP header values. Missing
  variables reject the connection. Resolved values never enter schemas, model messages,
  confirmations, logs, or returned error details.
- Runtime state is one of `disconnected`, `connecting`, `connected`, or `error`.
- Generated function names start with `mcp__`, match `[A-Za-z0-9_-]+`, are at most 64
  characters, and use a deterministic hash for truncation or collisions.
- Tool input schemas exposed to OpenAI are object schemas. Nested schema strings are redacted.
- Each connected server owns one long-lived worker coroutine. The worker enters and exits its
  AnyIO/MCP context managers in the same asyncio task.
- Initialization and discovery use `connect_timeout`; each list/call operation has its own
  `call_timeout`. The underlying SDK/HTTP read timeout must be at least the larger value so it
  does not preempt the operation-specific timeout.
- A call may reconnect before execution when no live connection exists. Do not retry after an
  ambiguous `tools/call` transport failure because the remote side effect may have completed.
- On Windows Conda builds, explicitly collect `libssl-3-x64.dll` and
  `libcrypto-3-x64.dll` from `sys.prefix/Library/bin` when present. Never take these DLLs from
  the base Conda installation when `_ssl.pyd` comes from an environment.
- PyInstaller collects the exact MCP client modules and `mcp` metadata. Do not collect
  `mcp.cli` unless the optional CLI dependencies are intentionally installed.

### 4. Validation & Error Matrix

| Condition | Required behavior |
| --- | --- |
| Duplicate server ID or name | Reject save with a configuration error |
| Enabled stdio server without command | Reject save/test |
| Enabled HTTP server without an HTTP(S) URL | Reject save/test |
| Missing `${ENV_VAR}` | Return the variable name, never a resolved secret |
| One server cannot connect | Mark only that server `error`; keep other tools available |
| Disabled server or disallowed tool | Exclude it from the next Agent schema list |
| Untrusted tool call | Use the existing confirmation callback with server/tool/arguments only |
| Trusted tool call | Execute without confirmation |
| Call timeout | Return an actionable redacted MCP error and close the failed worker |
| Config changes or app shutdown | Close affected sessions and stdio child processes |
| Structured or image result | Produce model-readable text or the existing image marker |
| Result over 60,000 characters | Truncate and state the original length |

### 5. Good / Base / Bad Cases

- Good: A stdio server receives configured env values while inheriting `PATH`, exposes an
  allowlisted tool, survives multiple chat messages, and terminates when disabled.
- Base: An empty `mcp_servers` list creates no workers and leaves all built-in tools unchanged.
- Bad: Passing only the configured env map to `StdioServerParameters` removes inherited `PATH`
  and makes commands such as `npx` fail.
- Bad: Entering a client context in one coroutine and closing it from another triggers AnyIO
  cancel-scope ownership errors.
- Bad: A Conda build packages base-environment OpenSSL DLLs next to an environment `_ssl.pyd`,
  causing `ImportError: DLL load failed while importing _ssl` at startup.

### 6. Tests Required

- Normalize valid configs and reject duplicate IDs/names and invalid transports/endpoints.
- Assert generated names are valid, bounded, deterministic, and collision-safe.
- Assert secrets are absent from nested schemas, results, confirmations, and error text.
- Start a local stdio server; verify discovery, allowlisting, inherited `PATH`, calls, timeout,
  config removal, child cleanup, and manager-thread shutdown.
- Start a local Streamable HTTP server; verify custom headers, discovery, calls, and status.
- Verify disabled servers create no workers and expose no schemas.
- Verify untrusted Agent routing can be rejected and trusted routing bypasses confirmation.
- Run `unittest`, `compileall`, JavaScript syntax checks, a clean Windows onedir build, and a
  packaged executable startup smoke test.

### 7. Wrong vs Correct

#### Wrong

```python
async with stdio_client(params) as streams:
    self.session = ClientSession(*streams)
# A different task later attempts to close or reuse these contexts.
```

```python
params = StdioServerParameters(command=command, env=configured_env)
# Replaces the child environment and can remove PATH.
```

#### Correct

```python
async def server_worker():
    async with AsyncExitStack() as stack:
        streams = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(*streams))
        await serve_commands(session)
```

```python
params = StdioServerParameters(
    command=command,
    env={**os.environ, **configured_env},
)
```
