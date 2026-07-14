# MCP client implementation plan

1. Add the stable MCP dependency and PyInstaller collection rules.
2. Implement configuration normalization, redaction, environment expansion, deterministic tool naming, result conversion, and the threaded asynchronous MCP manager.
3. Wire the shared manager into API lifecycle, config saving, server test/status/reconnect bridge methods, and Agent construction.
4. Merge dynamic schemas into Agent tools and route MCP calls through the existing confirmation and ReAct result path.
5. Add the MCP settings tab with structured stdio/HTTP editors, masked key-value fields, runtime status, connection testing, and per-tool selection.
6. Add standard-library unit tests and local stdio/Streamable HTTP integration fixtures.
7. Run `python -m unittest discover -s tests -v`, `python -m compileall app tests`, and `pyinstaller QuickModel.spec --clean`; inspect the packaged application for MCP imports and process cleanup.
8. Run the Trellis quality check and record any reusable MCP lifecycle or packaging conventions in project specs.

## Rollback Points

- MCPManager is isolated in a new module and can be disabled by an empty `mcp_servers` list.
- Agent dynamic routing is additive and leaves existing `TOOLS_SCHEMA` and `dispatch` behavior unchanged.
- UI state persists only after the normal settings Save action.
