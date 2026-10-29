"""Raw-wire tour of the running example (no SDK client).

EDUCATIONAL SKETCH, NOT PRODUCTION CODE. It shows what 2026-07-28 requests
look like on the wire: no handshake, no session id, every request carries its
own protocol version and capabilities, and `Mcp-Method` / `Mcp-Name` headers
mirror the body so gateways can route without parsing JSON.

Start the server first (`uv run basket_server.py`), then run this file.
Needs `uv add httpx`.
"""

import json
from typing import Any

import httpx

URL = "http://127.0.0.1:8000/mcp"
VERSION = "2026-07-28"

JsonObject = dict[str, Any]


def rpc(
    client: httpx.Client,
    token: str | None,
    request_id: int,
    method: str,
    params: JsonObject | None = None,
) -> JsonObject:
    """POST one JSON-RPC request and return the decoded response object."""
    body_params: JsonObject = dict(params or {})
    body_params["_meta"] = {
        "io.modelcontextprotocol/protocolVersion": VERSION,
        "io.modelcontextprotocol/clientCapabilities": {"elicitation": {}},
        "io.modelcontextprotocol/clientInfo": {"name": "wire-demo", "version": "0.1"},
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": VERSION,
        "Mcp-Method": method,
    }
    if method == "tools/call":
        headers["Mcp-Name"] = str(body_params["name"])
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": body_params,
    }
    response = client.post(URL, headers=headers, json=payload)
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        # A request-scoped SSE stream: the last data line is the final response.
        data_lines = [
            line[5:].strip()
            for line in response.text.splitlines()
            if line.startswith("data:")
        ]
        decoded: JsonObject = json.loads(data_lines[-1])
        return decoded
    decoded = response.json()
    return decoded


def show(title: str, value: object) -> None:
    print(f"\n--- {title}")
    print(json.dumps(value, indent=2))


def main() -> None:
    with httpx.Client(timeout=10.0) as client:
        # 1. Discovery is optional, and needs no handshake or session.
        show("server/discover", rpc(client, "alice-token", 1, "server/discover"))

        # 2. A tool call is one self-contained POST.
        created = rpc(
            client,
            "alice-token",
            2,
            "tools/call",
            {"name": "create_basket", "arguments": {}},
        )
        basket_id: str = created["result"]["structuredContent"]["basket_id"]
        show("create_basket (the handle is an ordinary tool result)", created["result"])

        # 3. Pass the handle back as an ordinary argument.
        for request_id, sku, qty in ((3, "coffee", 2), (4, "bread", 1)):
            args: JsonObject = {"basket_id": basket_id, "sku": sku, "quantity": qty}
            rpc(
                client,
                "alice-token",
                request_id,
                "tools/call",
                {"name": "add_item", "arguments": args},
            )

        # 4. A large order: the server returns input_required instead of a result.
        first = rpc(
            client,
            "alice-token",
            5,
            "tools/call",
            {"name": "checkout", "arguments": {"basket_id": basket_id}},
        )
        show("checkout, round 1 (input_required)", first["result"])

        # 5. Retry the SAME call with a NEW id, the answers, and the echoed state.
        result = first["result"]
        answers: JsonObject = {
            key: {"action": "accept", "content": {"ok": True}}
            for key in result["inputRequests"]
        }
        retry_params: JsonObject = {
            "name": "checkout",
            "arguments": {"basket_id": basket_id},
            "inputResponses": answers,
            "requestState": result["requestState"],
        }
        second = rpc(client, "alice-token", 6, "tools/call", retry_params)
        show("checkout, round 2 (complete)", second["result"])


if __name__ == "__main__":
    main()
