# Architecture and engineering walkthrough

## Scope

AIRI is a local coordinator with optional compute workers. `server.py` owns the browser API,
conversation state and approval decisions. `llm_client.py` handles model requests. The UI,
records, schedules, camera and file operations stay on the coordinator even when inference
runs on a paired computer; device selection is not full-host failover.

The loopback host validates browser sessions before serving authenticated JSON operations.
The community launcher uses port 8766 and an independent data directory; `run.py --standby`
starts the inspection host without normal background workers. It does not migrate another
installation or read that installation's account keys. SQLite files belong on a suitable
local filesystem; workers exchange requests rather than share a live database. Embedded
Stock101 keeps PAPER and LIVE records separate. Telegram, camera and voice services require
their own setup.

## Tool and approval path

1. `agent_runtime.py` exposes a named tool registry and a bounded model/tool loop: at most
   four rounds, with at most four tool calls per round. Social turns can use a simpler path.
2. `execute()` calls the shared permission gate before dispatch. Unknown tools are blocked.
   Bounded read tools may execute immediately; local reversible operations have a separate tier.
3. `request_api_call` validates an enabled registered API and creates an approval record.
   `request_mcp_call` discovers a registered server's tools and prepares an approval for the
   selected tool. Discovery can contact the server; the requested tool is not executed yet.
4. Both requests return `pending_user_approval` and `executed: false`. The UI displays the
   pending request. `server.decide()` dispatches the registered API/MCP tool after approval.
5. The result is persisted. A failed or uncertain call is not represented as a completed action.

This describes the named API/MCP request path, not a claim that every optional connector
has identical behavior. Registered MCP programs and endpoints are user-configured trusted
integrations. Prompt instructions alone are not a security boundary.

| Responsibility | Implementation | Review evidence |
| --- | --- | --- |
| Tool registry, dispatch and bounded model loop | [`agent_runtime.py`](../agent_runtime.py) | [`test_tool_approval_boundary.py`](../tests/test_tool_approval_boundary.py) |
| MCP registration, HTTP/stdio discovery and preparation | [`mcp_bridge.py`](../mcp_bridge.py), [`scripts/mcp_client.py`](../scripts/mcp_client.py) | `prepare()` records the request before execution |
| Registered HTTP API requests | [`automation.py`](../automation.py) | `create_approval()` and `run_tool()` are separate operations |
| Permission tiers and audit trail | [`permissions.py`](../airi_core/execution/permissions.py) | Expiry, argument signatures and single-use approval tracking |
| Approval decisions and local records | [`server.py`](../server.py) | `decide()` records executing, rejected, done or unknown states |
| Automatic inference routing | [`devices.py`](../devices.py), [`device_transport.py`](../device_transport.py) | [`test_devices.py`](../tests/test_devices.py) checks TLS, pairing, health and stream fallback |

## Try a small example

Start the application, choose an installed local model and ask it to read your saved tasks.
A new profile should report no saved tasks, not invent a schedule. Add a task through the UI
and ask again. Configure your own API/MCP service only when needed; the request and approval
screen should be inspected before allowing it to run. No example credentials are bundled.

## Design decisions and limits

- **One coordinator:** simpler local ownership of records; it must stay running. Paired
  devices supply inference capacity, not database replication or automatic app migration.
- **Explicit results:** queued work and pending approval are distinct from completion.
- **Bounded context and tool rounds:** control latency and repeated work; complex tasks
  may need another user turn or a dedicated workflow.
- **Optional integrations:** camera, neural voice, Telegram and external tools need their
  own setup. Their full combinations are not certified by the unit suite.
- **Maintainability:** the main agent runtime now has expanded formatting, typed function
  boundaries and targeted approval tests. Legacy modules are still being modernized.

See [feature requirements](FEATURES.md), [device protocol](DEVICES.md) and
[actual release checks](VALIDATION.md). The screenshot in the README is an actual clean
community installation, not the original owner's environment.
