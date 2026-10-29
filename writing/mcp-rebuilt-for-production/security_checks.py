"""Executable security checks for the running example.

EDUCATIONAL SKETCH, NOT A TEST SUITE. Each check demonstrates one attack from
the article and the control that stops it. Start the server first
(`uv run basket_server.py`), then run this file. Needs `uv add httpx`.
"""

from typing import Any

import httpx

from wire_demo import URL, VERSION, JsonObject, rpc


def call_tool(
    client: httpx.Client,
    token: str | None,
    request_id: int,
    name: str,
    arguments: JsonObject,
) -> JsonObject:
    return rpc(
        client, token, request_id, "tools/call", {"name": name, "arguments": arguments}
    )


def tool_text(response: JsonObject) -> str:
    content: list[JsonObject] = response["result"]["content"]
    return str(content[0]["text"])


def report(label: str, passed: bool, detail: str) -> None:
    print(f"[{'PASS' if passed else 'FAIL'}] {label}: {detail}")


def main() -> None:
    with httpx.Client(timeout=10.0) as client:
        # 0. Setup: Alice creates a basket worth more than the confirmation threshold.
        created = call_tool(client, "alice-token", 1, "create_basket", {})
        basket_id: str = created["result"]["structuredContent"]["basket_id"]
        call_tool(
            client,
            "alice-token",
            2,
            "add_item",
            {"basket_id": basket_id, "sku": "coffee"},
        )
        call_tool(
            client,
            "alice-token",
            20,
            "add_item",
            {"basket_id": basket_id, "sku": "apple", "quantity": 2},
        )

        # 1. No token: refused at the door, before any tool code runs.
        raw = client.post(
            URL, json={}, headers={"Accept": "application/json, text/event-stream"}
        )
        report("no token", raw.status_code == 401, f"HTTP {raw.status_code}")

        # 2. Token issued for another server: audience binding rejects it.
        raw = client.post(
            URL,
            json={},
            headers={
                "Authorization": "Bearer elsewhere-token",
                "Accept": "application/json, text/event-stream",
            },
        )
        report(
            "wrong-audience token", raw.status_code == 401, f"HTTP {raw.status_code}"
        )

        # 3. State handle hijacking: Bob presents Alice's valid handle.
        stolen = call_tool(
            client, "bob-token", 3, "view_basket", {"basket_id": basket_id}
        )
        guess = call_tool(
            client, "bob-token", 4, "view_basket", {"basket_id": "not-a-real-id"}
        )
        stolen_msg, guess_msg = tool_text(stolen), tool_text(guess)
        report("handle hijacking", stolen["result"]["isError"], stolen_msg)
        report(
            "no existence oracle",
            stolen_msg == guess_msg,
            "stolen and made-up ids look identical",
        )

        # 4. Scope enforcement: Carol holds only basket:read.
        denied = call_tool(client, "carol-token", 5, "create_basket", {})
        report("missing scope", denied["result"]["isError"], tool_text(denied))

        # 5. requestState tampering and cross-principal replay.
        first = call_tool(
            client, "alice-token", 6, "checkout", {"basket_id": basket_id}
        )
        state: str = first["result"]["requestState"]
        answers: JsonObject = {
            key: {"action": "accept", "content": {"ok": True}}
            for key in first["result"]["inputRequests"]
        }

        def retry(token: str, request_id: int, request_state: str) -> JsonObject:
            params: JsonObject = {
                "name": "checkout",
                "arguments": {"basket_id": basket_id},
                "inputResponses": answers,
                "requestState": request_state,
            }
            return rpc(client, token, request_id, "tools/call", params)

        flipped = state[:-4] + ("AAAA" if not state.endswith("AAAA") else "BBBB")
        tampered = retry("alice-token", 7, flipped)
        error: Any = tampered.get("error")
        report(
            "tampered requestState",
            error is not None and error.get("code") == -32602,
            str(error),
        )

        replayed = retry("bob-token", 8, state)
        error = replayed.get("error")
        report("state replayed by another user", error is not None, str(error))

        # 6. Header/body mismatch (a gateway and the server must agree on the method).
        mismatch = client.post(
            URL,
            headers={
                "Authorization": "Bearer alice-token",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": VERSION,
                "Mcp-Method": "tools/list",  # header says list ...
                "Mcp-Name": "view_basket",
            },
            json={
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",  # ... body says call
                "params": {
                    "name": "view_basket",
                    "arguments": {"basket_id": basket_id},
                    "_meta": {
                        "io.modelcontextprotocol/protocolVersion": VERSION,
                        "io.modelcontextprotocol/clientCapabilities": {},
                    },
                },
            },
        )
        report(
            "header/body mismatch",
            mismatch.status_code == 400,
            f"HTTP {mismatch.status_code} {mismatch.text[:120]}",
        )

        # 7. The legitimate flow still works end to end.
        final = retry("alice-token", 10, state)
        report("legitimate retry", not final["result"]["isError"], tool_text(final))


if __name__ == "__main__":
    main()
