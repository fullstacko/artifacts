"""A minimal SDK client for the running example.

EDUCATIONAL SKETCH, NOT PRODUCTION CODE. The token is hard-coded; a real
client discovers the authorization server and obtains a token through OAuth.
It shows the host's job in the multi round-trip flow: when the server returns
`input_required`, a human (here, a callback) answers, and the SDK retries.

Start the server first (`uv run basket_server.py`), then run this file.
"""

import asyncio

import httpx2
from mcp import Client
from mcp.client import ClientRequestContext
from mcp.client.streamable_http import streamable_http_client
from mcp.types import ElicitRequestFormParams, ElicitRequestParams, ElicitResult

URL = "http://127.0.0.1:8000/mcp"


async def ask_human(
    context: ClientRequestContext, params: ElicitRequestParams
) -> ElicitResult:
    """Called when the server needs input. A real host would render a form."""
    if isinstance(params, ElicitRequestFormParams):
        print(f"Server asks: {params.message}")
        return ElicitResult(action="accept", content={"ok": True})
    # URL-mode elicitation (payments, OAuth consent) must go to the user's browser.
    return ElicitResult(action="decline")


async def main() -> None:
    http_client = httpx2.AsyncClient(
        headers={"Authorization": "Bearer alice-token"}, timeout=30.0
    )
    transport = streamable_http_client(URL, http_client=http_client)
    async with Client(transport, elicitation_callback=ask_human) as client:
        print("protocol version:", client.protocol_version)

        created = await client.call_tool("create_basket", {})
        structured = created.structured_content or {}
        basket_id = str(structured["basket_id"])

        await client.call_tool(
            "add_item", {"basket_id": basket_id, "sku": "coffee", "quantity": 2}
        )
        await client.call_tool("add_item", {"basket_id": basket_id, "sku": "bread"})

        # The SDK runs the retry loop; the elicitation callback fires in between.
        result = await client.call_tool("checkout", {"basket_id": basket_id})
        print("checkout:", result.structured_content)


if __name__ == "__main__":
    asyncio.run(main())
