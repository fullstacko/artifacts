"""Running example for the MCP deep dive: a tiny shopping-basket server.

EDUCATIONAL SKETCH, NOT PRODUCTION CODE. It keeps state in process memory,
uses a hard-coded token table instead of a real authorization server, and has
no persistence, rate limiting, or audit logging. Use it to understand the
concepts in the article, then build the real thing properly.

Run (Python 3.10+, `uv add "mcp>=2,<3"`)::

    uv run basket_server.py            # serves http://127.0.0.1:8000/mcp
"""

import secrets
import time
from dataclasses import dataclass, field
from typing import Annotated

from mcp.server import CacheHint, MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
    Elicit,
    ElicitationResult,
    Resolve,
)
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import AnyHttpUrl, BaseModel

RESOURCE_URL = "http://127.0.0.1:8000/mcp"
CATALOG: dict[str, int] = {"apple": 120, "bread": 350, "coffee": 899}  # price in cents
BASKET_TTL_SECONDS = 24 * 60 * 60
CONFIRM_ABOVE_CENTS = 1000  # checkouts above this total ask the user first

SCOPE_READ = "basket:read"
SCOPE_WRITE = "basket:write"
SCOPE_CHECKOUT = "basket:checkout"


# --- Identity (section: authorization) ---------------------------------------
# A stand-in for a real authorization server. In production the verifier would
# validate a signed JWT or call the token-introspection endpoint, and report
# the token's audience in `AccessToken.resource`.
def _demo_token(name: str, scopes: list[str]) -> AccessToken:
    return AccessToken(
        token=f"{name}-token",
        client_id="demo-client",
        subject=name,
        scopes=scopes,
        resource=RESOURCE_URL,
    )


DEMO_TOKENS: dict[str, AccessToken] = {
    "alice-token": _demo_token("alice", [SCOPE_READ, SCOPE_WRITE, SCOPE_CHECKOUT]),
    "bob-token": _demo_token("bob", [SCOPE_READ, SCOPE_WRITE, SCOPE_CHECKOUT]),
    "carol-token": _demo_token("carol", [SCOPE_READ]),  # read-only
    # A valid token, but issued for a DIFFERENT server. With
    # validate_token_resource=True the SDK refuses it (audience binding).
    "elsewhere-token": AccessToken(
        token="elsewhere-token",
        client_id="demo-client",
        subject="alice",
        scopes=[SCOPE_READ, SCOPE_WRITE, SCOPE_CHECKOUT],
        resource="https://other.example.com/mcp",
    ),
}


class DemoTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        return DEMO_TOKENS.get(token)


# --- State (section: stateless protocol, stateful app) -----------------------
@dataclass
class Basket:
    items: dict[str, int] = field(default_factory=dict)
    expires_at: float = 0.0


# Keyed by "<subject>:<basket_id>". The subject comes from the verified token,
# never from anything the client or model sends. Possessing a basket_id proves
# nothing on its own.
_BASKETS: dict[str, Basket] = {}


def _require(scope: str) -> str:
    """Return the caller's subject, or raise a tool execution error."""
    token = get_access_token()
    if token is None or token.subject is None:
        raise ToolError("Authentication required.")
    if scope not in token.scopes:
        # Simplified. A fuller server would answer 403 + WWW-Authenticate
        # (error="insufficient_scope", scope="...") so the client can step up.
        raise ToolError(f"This action needs the '{scope}' scope.")
    return token.subject


def _basket_key(subject: str, basket_id: str) -> str:
    return f"{subject}:{basket_id}"


def _load(subject: str, basket_id: str) -> Basket:
    basket = _BASKETS.get(_basket_key(subject, basket_id))
    if basket is None or basket.expires_at < time.time():
        # Same message for "never existed", "expired" and "not yours", so a
        # guessing attacker learns nothing. Phrased so the model can recover.
        raise ToolError(
            "Unknown or expired basket_id. Call create_basket to start a new one."
        )
    return basket


def _total_cents(basket: Basket) -> int:
    return sum(CATALOG[sku] * qty for sku, qty in basket.items.items())


class BasketView(BaseModel):
    basket_id: str
    items: dict[str, int]
    total_cents: int


def _view(basket_id: str, basket: Basket) -> BasketView:
    return BasketView(
        basket_id=basket_id, items=dict(basket.items), total_cents=_total_cents(basket)
    )


# --- Server ------------------------------------------------------------------
mcp = MCPServer(
    "Corner Shop",
    instructions="Create a basket, add catalogue items to it, then check out.",
    token_verifier=DemoTokenVerifier(),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl("https://auth.example.com"),
        resource_server_url=AnyHttpUrl(RESOURCE_URL),
        required_scopes=[SCOPE_READ],  # baseline for every token
        validate_token_resource=True,  # refuse tokens issued for other servers
    ),
    # tools/list may vary with the caller's scopes, so keep the cache private.
    cache_hints={"tools/list": CacheHint(ttl_ms=300_000, scope="private")},
    # Single process: the SDK seals requestState under a per-process key.
    # Several instances or restarts: pass
    # request_state_security=RequestStateSecurity(keys=[...]) with a shared secret.
)


@mcp.resource("catalog://items")
def catalog() -> dict[str, int]:
    """The catalogue: SKU -> price in cents."""
    return CATALOG


@mcp.prompt()
def shopping_assistant(budget_cents: int) -> str:
    """Prompt template: help the user shop within a budget."""
    return (
        f"You are a shopping assistant. The user's budget is {budget_cents} cents. "
        "Use the basket tools, and never exceed the budget."
    )


@mcp.tool()
def create_basket() -> BasketView:
    """Create an empty basket and return its basket_id.

    Pass basket_id to the other basket tools. Baskets expire after 24 hours.
    """
    subject = _require(SCOPE_WRITE)
    basket_id = secrets.token_urlsafe(16)  # unguessable, opaque, no structure
    basket = Basket(expires_at=time.time() + BASKET_TTL_SECONDS)
    _BASKETS[_basket_key(subject, basket_id)] = basket
    return _view(basket_id, basket)


@mcp.tool()
def add_item(basket_id: str, sku: str, quantity: int = 1) -> BasketView:
    """Add a catalogue item (see catalog://items) to a basket."""
    subject = _require(SCOPE_WRITE)
    basket = _load(subject, basket_id)
    if sku not in CATALOG:
        raise ToolError(
            f"Unknown sku {sku!r}. Valid skus: {', '.join(sorted(CATALOG))}."
        )
    if not 1 <= quantity <= 20:
        raise ToolError("quantity must be between 1 and 20.")
    basket.items[sku] = basket.items.get(sku, 0) + quantity
    return _view(basket_id, basket)


@mcp.tool()
def view_basket(basket_id: str) -> BasketView:
    """Show the contents and total of a basket."""
    subject = _require(SCOPE_READ)
    return _view(basket_id, _load(subject, basket_id))


# --- Multi round-trip request (section: MRTR) --------------------------------
class Confirm(BaseModel):
    ok: bool


async def confirm_checkout(basket_id: str) -> Confirm | Elicit[Confirm]:
    """Resolver: only interrupt the user when the order is large.

    The resolver reads the tool's own `basket_id` argument by name. On a
    2026-07-28 connection the SDK turns Elicit(...) into an InputRequiredResult
    and the client retries with the answer; this function never knows the
    difference. The question text depends on the basket's contents, so if the
    basket changes between rounds the server re-asks instead of reusing a
    stale answer.
    """
    subject = _require(SCOPE_CHECKOUT)
    total = _total_cents(_load(subject, basket_id))
    if total <= CONFIRM_ABOVE_CENTS:
        return Confirm(ok=True)  # no round trip needed
    return Elicit(f"Place an order for {total} cents?", Confirm)


@mcp.tool()
async def checkout(
    basket_id: str,
    confirm: Annotated[ElicitationResult[Confirm], Resolve(confirm_checkout)],
) -> str:
    """Place the order for a basket. Asks the user to confirm large orders."""
    subject = _require(SCOPE_CHECKOUT)
    match confirm:
        case AcceptedElicitation(data=Confirm(ok=True)):
            basket = _load(subject, basket_id)
            total = _total_cents(basket)
            del _BASKETS[_basket_key(subject, basket_id)]
            return f"Order placed: {total} cents."
        case AcceptedElicitation():
            return "Order not placed: you chose not to confirm."
        case DeclinedElicitation():
            return "Order not placed: confirmation declined."
        case CancelledElicitation():
            return "Order not placed: confirmation cancelled."


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
