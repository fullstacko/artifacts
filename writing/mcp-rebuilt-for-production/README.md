# Running example ("Corner Shop" basket server)

> **Educational sketches, not production code.** In-memory state, a hard-coded
> token table instead of a real authorization server, no persistence, rate
> limiting or audit logging. Use these files to understand the concepts, then
> build the real thing properly.

Verified against the MCP Python SDK `mcp` 2.3.0 and spec revision `2026-07-28`
on Python 3.12. All files pass `ruff check`, `ruff format` and `mypy --strict`.

See the [main article](https://www.fullstacko.com/writing/mcp-rebuilt-for-production) for context and explanations.

## Setup

```bash
uv init --bare --python 3.12
uv add "mcp>=2,<3" httpx
```

This needs [uv](https://docs.astral.sh/uv/). It creates `.venv` and
`pyproject.toml` on first use; `uv run` below uses that environment.

## Files

| File | Article section | What it shows |
| - | - | - |
| `basket_server.py` | Build, state, MRTR, authorization | Server with tools, resource, prompt, token verifier, scopes, explicit state handle, confirmation via multi round-trip request, cache hints |
| `wire_demo.py` | The protocol on the wire | Raw JSON-RPC over HTTP: no handshake, `_meta`, `Mcp-Method`/`Mcp-Name`, `input_required` and the retry |
| `basket_client.py` | Building a client | SDK client with an Authorization header and an elicitation callback |
| `security_checks.py` | Security | Executable checks: missing token, wrong audience, handle hijacking, scope, tampered/replayed `requestState`, header mismatch |
| `tool_pins.py` | Security (client side) | Fingerprinting tool definitions to catch tool poisoning and rug pulls |

## Run

```bash
uv run basket_server.py          # terminal 1: http://127.0.0.1:8000/mcp
uv run wire_demo.py              # terminal 2
uv run basket_client.py
uv run security_checks.py
uv run tool_pins.py              # no server needed
```

Demo tokens: `alice-token` and `bob-token` (full access), `carol-token`
(read-only), `elsewhere-token` (valid, but issued for a different server).
