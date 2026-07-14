# Add MCP client support

## Goal

Add MCP tool calling to QuickModel so enabled local and remote MCP servers can expose tools directly to the existing multi-round Agent workflow.

## Requirements

- Use the stable official Python SDK with `mcp>=1.28.1,<2`.
- Support stdio and Streamable HTTP transports. Legacy SSE is out of scope.
- Support MCP Tools only through initialize, tools/list, and tools/call.
- Keep MCP sessions alive across chat messages, connect lazily, and cleanly close replaced or removed sessions.
- Expose discovered tools as individual OpenAI-compatible function schemas with deterministic names and internal original-name mappings.
- Let users configure, enable, test, reconnect, trust, and filter tools for each server from a structured MCP settings tab.
- Require confirmation for every call from an untrusted server; trusted servers may execute without confirmation.
- Persist MCP secrets consistently with existing application API keys, mask them in the UI, support `${ENV_VAR}` expansion, and never expose resolved secrets to the model, confirmations, results, or logs.
- Normalize text, structured, image, and unsupported binary results into the application's existing tool-result conventions, with a 60,000-character output limit.
- A failed server must not prevent other MCP servers or built-in tools from working.

## Acceptance Criteria

- [x] A configured stdio server can be tested, discovered, and called from the Agent ReAct loop.
- [x] A configured Streamable HTTP server can be tested, discovered, and called from the Agent ReAct loop.
- [x] Tool names are valid, deterministic, collision-safe, and no longer than 64 characters.
- [x] Disabled servers and filtered tools are absent from the next Agent request.
- [x] Untrusted calls show the existing confirmation flow; trusted calls bypass it.
- [x] Missing environment variables, connection failures, timeouts, and MCP errors return actionable redacted messages.
- [x] Configuration changes close obsolete sessions and application shutdown does not leave stdio child processes running.
- [x] Unit/integration tests, compile checks, and the Windows PyInstaller build pass.

## Out of Scope

- MCP Resources, Prompts, Sampling, Elicitation, OAuth, server marketplaces, and Claude Desktop JSON import.
- Version bump, release tag, or GitHub Release publication.
