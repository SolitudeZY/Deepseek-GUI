# MCP client technical design

## Architecture

`API` owns one long-lived `MCPManager`. The manager runs an asyncio event loop on a dedicated daemon thread and owns all MCP transports and ClientSession instances. Agent objects remain short-lived per message and receive the shared manager.

The manager lazily connects enabled servers when Agent requests tool schemas. It initializes the session, lists tools, caches server metadata and schemas, and returns OpenAI function schemas. A call resolves the generated name back to `(server_id, original_tool_name)` and submits tools/call on the manager loop.

## Configuration Contract

Each `mcp_servers` entry contains stable `id`, unique display `name`, `enabled`, `transport`, `trusted`, connect/call timeouts, `tool_policy`, `enabled_tools`, and transport-specific `stdio` and `http` objects. `tool_policy=all` exposes every discovered tool; `allowlist` exposes only `enabled_tools` and excludes newly discovered tools until selected.

Environment and header values expand `${NAME}` immediately before process or HTTP client creation. Unresolved variables reject connection without showing any resolved secret values.

## Tool Contract

Generated names start with `mcp__`, contain only letters, digits, `_`, and `-`, and stay within 64 characters. Sanitized collisions and long names receive a deterministic short SHA-256 suffix. The input schema comes from MCP `inputSchema`, normalized to an object schema when malformed or absent.

Agent combines MCP schemas with built-in schemas, sorts them deterministically, and caches them for that Agent instance. A newly created Agent therefore observes the latest saved MCP configuration without mutating schemas mid-request.

## Safety And Failure Handling

Dynamic MCP calls are routed before built-in dispatch. Calls from untrusted servers invoke the existing confirmation callback with only server name, original tool name, and model-supplied arguments. Server configuration, headers, env values, and resolved secrets are excluded.

Connections use 15-second defaults and calls use 60-second defaults. A disconnected call reconnects once. Server errors update runtime status but do not remove other servers. Results are normalized and truncated at 60,000 characters. Image blocks are saved under the application uploads area and returned using the existing image marker.

Configuration replacement closes changed/removed sessions. API shutdown closes all sessions and transports so stdio process trees terminate through the SDK.

## Compatibility

Pin SDK to the stable v1 line. Collect MCP submodules and package metadata in Windows and macOS PyInstaller specs. Existing static tools and config files without `mcp_servers` continue to work through the default empty list.
