import asyncio
import json
import logging
import os
import re
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

logger = logging.getLogger("comparison")
logging.basicConfig(level=logging.INFO)

# Upstream MCP servers (override with env vars on Render if the URLs change).
SWIGGY_URL = os.getenv("SWIGGY_MCP_URL", "https://food-swiggy-mcp.onrender.com/mcp")
ZOMATO_URL = os.getenv("ZOMATO_MCP_URL", "https://food-zomato-mcp.onrender.com/mcp")

# Free-tier Render services can take 30-60s to wake up.
UPSTREAM_TIMEOUT_SECONDS = float(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "60"))
UPSTREAM_ATTEMPTS = 2

# Render sets PORT automatically and needs the server bound to 0.0.0.0.
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8003"))

# Host validation: allow this service's public hostname.
PUBLIC_HOST = os.getenv(
    "RENDER_EXTERNAL_HOSTNAME", "food-comparison-mcp.onrender.com"
)
transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[
        PUBLIC_HOST, f"{PUBLIC_HOST}:*",
        "127.0.0.1:*", "localhost:*",
    ],
    allowed_origins=[
        f"https://{PUBLIC_HOST}",
        "http://127.0.0.1:*", "http://localhost:*",
    ],
)

mcp = FastMCP(
    "Food Price Comparison",
    host=HOST,
    port=PORT,
    transport_security=transport_security,
)

# ---------------------------------------------------------------------------
# Query cleaning
# ---------------------------------------------------------------------------
# Upstream search is a plain substring match on name+category+description, so
# words like "food" or "vegetarian dishes" match nothing. Drop filler words.
FILLER_WORDS = {
    "a", "an", "the", "some", "any", "me", "my", "i", "for", "of", "in", "on",
    "under", "below", "within", "upto", "up", "to", "max", "maximum", "budget",
    "food", "foods", "dish", "dishes", "item", "items", "meal", "meals",
    "veg", "vegetarian", "suggest", "recommend", "show", "find", "get",
    "cheap", "cheapest", "best", "good", "options", "option", "rs", "inr",
    "rupees", "and", "or", "with",
}


def clean_query(query: str) -> list[str]:
    """Return meaningful search tokens ([] means 'match everything')."""
    tokens = re.findall(r"[a-z0-9]+", (query or "").lower())
    return [t for t in tokens if t not in FILLER_WORDS and not t.isdigit()]


def matches_tokens(item: dict[str, Any], tokens: list[str]) -> bool:
    text = " ".join(
        str(item.get(k, "")) for k in ("name", "category", "description")
    ).lower()
    return all(t in text for t in tokens)


def select_items(items: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Pick the items a query refers to.

    A multi-word query that is part of a dish name (for example
    "Veg Dum Biryani") selects exactly those dishes. Otherwise fall back to
    keyword matching with filler words removed.
    """
    words = re.findall(r"[a-z0-9]+", (query or "").lower())
    if len(words) >= 2:
        phrase = " ".join(words)
        exact = [
            i for i in items
            if phrase in " ".join(
                re.findall(r"[a-z0-9]+", str(i.get("name", "")).lower())
            )
        ]
        if exact:
            return exact
    tokens = clean_query(query)
    return [i for i in items if matches_tokens(i, tokens)]


# ---------------------------------------------------------------------------
# Upstream calls with real error reporting
# ---------------------------------------------------------------------------
def flatten_exception(exc: BaseException) -> list[str]:
    """Unwrap (nested) ExceptionGroups so the real cause is visible."""
    subs = getattr(exc, "exceptions", None)
    if subs:
        out: list[str] = []
        for sub in subs:
            out.extend(flatten_exception(sub))
        return out
    return [f"{type(exc).__name__}: {exc}"]


async def _call_once(
    server_url: str, tool_name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    async with streamablehttp_client(server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=arguments)

            if result.isError:
                detail = " ".join(
                    getattr(c, "text", "") or "" for c in result.content
                )
                raise RuntimeError(f"{tool_name} returned an error: {detail}")

            for content in result.content:
                text = getattr(content, "text", None)
                if text:
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(data, dict) and data.get("error"):
                        raise RuntimeError(
                            f"{tool_name} reported: {data['error']}"
                        )
                    return data

            raise RuntimeError(f"No JSON result returned by {tool_name}")


async def call_remote_tool(
    server_url: str, tool_name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Call an upstream tool; raise RuntimeError with the real cause."""
    last_error = "unknown error"
    for attempt in range(1, UPSTREAM_ATTEMPTS + 1):
        try:
            return await asyncio.wait_for(
                _call_once(server_url, tool_name, arguments),
                timeout=UPSTREAM_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            last_error = f"timed out after {UPSTREAM_TIMEOUT_SECONDS:.0f}s"
        except BaseException as exc:  # includes ExceptionGroup
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            last_error = "; ".join(flatten_exception(exc))
        logger.warning(
            "upstream %s %s attempt %d/%d failed: %s",
            server_url, tool_name, attempt, UPSTREAM_ATTEMPTS, last_error,
        )
    raise RuntimeError(last_error)


async def search_both_platforms(
    arguments: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Search both platforms. Returns (successes, errors) by platform."""
    platforms = {"Swiggy": SWIGGY_URL, "Zomato": ZOMATO_URL}
    outcomes = await asyncio.gather(
        *(
            call_remote_tool(url, "search_menu_items", arguments)
            for url in platforms.values()
        ),
        return_exceptions=True,
    )
    ok: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    for name, outcome in zip(platforms, outcomes):
        if isinstance(outcome, BaseException):
            errors[name] = str(outcome)
        else:
            ok[name] = outcome
    return ok, errors


def upstream_failure(errors: dict[str, str]) -> dict[str, Any]:
    return {
        "error": "Could not retrieve data from the upstream platforms.",
        "platform_errors": errors,
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@mcp.tool()
async def compare_menu_prices(
    query: str = "",
    max_price: float = 0,
    vegetarian_only: bool = False,
) -> dict[str, Any]:
    """Compare matching dishes and prices on Swiggy and Zomato.

    Matches the same dish by menu item ID. Compares listed menu prices only,
    not final checkout totals. Use a dish/cuisine keyword such as "biryani".
    """
    tokens = clean_query(query)

    ok, errors = await search_both_platforms(
        {"query": "", "max_price": max_price,
         "vegetarian_only": vegetarian_only}
    )
    if len(ok) < 2:
        return upstream_failure(errors)

    def items_of(platform: str) -> list[dict[str, Any]]:
        return select_items(ok[platform].get("items", []), query)

    zomato_by_id = {i["id"]: i for i in items_of("Zomato")}
    comparisons = []

    for sw in items_of("Swiggy"):
        zo = zomato_by_id.get(sw["id"])
        if not zo:
            continue
        sw_price, zo_price = float(sw["price"]), float(zo["price"])
        if sw_price < zo_price:
            cheaper = "Swiggy"
        elif zo_price < sw_price:
            cheaper = "Zomato"
        else:
            cheaper = "Same price"
        comparisons.append({
            "dish": sw["name"],
            "restaurant": sw.get("restaurant_name", "Unknown restaurant"),
            "swiggy_price": sw_price,
            "zomato_price": zo_price,
            "difference_rupees": round(abs(sw_price - zo_price), 2),
            "cheaper_platform": cheaper,
            "is_vegetarian": sw.get("is_vegetarian"),
        })

    comparisons.sort(key=lambda c: min(c["swiggy_price"], c["zomato_price"]))

    return {
        "query": query,
        "search_terms_used": tokens,
        "matched_dish_count": len(comparisons),
        "comparisons": comparisons,
        "notice": (
            "Fictional sample data. Prices are menu prices only; "
            "fees, taxes, delivery charges and coupon eligibility "
            "are not included."
        ),
    }


@mcp.tool()
async def recommend_food_within_budget(
    budget: float,
    query: str = "",
    vegetarian_only: bool = False,
) -> dict[str, Any]:
    """Find dishes on Swiggy and Zomato whose listed price is <= budget.

    query is optional: use only a dish/cuisine keyword such as "biryani" or
    "pizza". Leave it empty for no keyword. Set vegetarian_only=true for
    vegetarian requests. Listed dish prices only; no fees or taxes.
    """
    try:
        budget = float(budget)
    except (TypeError, ValueError):
        return {"error": f"Budget must be a number, got: {budget!r}"}
    if budget <= 0:
        return {"error": "Budget must be greater than zero."}

    tokens = clean_query(query)

    ok, errors = await search_both_platforms(
        {"query": "", "max_price": 0, "vegetarian_only": vegetarian_only}
    )
    if not ok:
        return upstream_failure(errors)

    recommendations = []
    for platform, response in ok.items():
        for item in select_items(response.get("items", []), query):
            price = float(item["price"])
            if price <= budget:
                recommendations.append({
                    "platform": platform,
                    "dish": item["name"],
                    "restaurant": item.get("restaurant_name",
                                           "Unknown restaurant"),
                    "price": price,
                    "budget_remaining": round(budget - price, 2),
                    "is_vegetarian": item.get("is_vegetarian"),
                })

    recommendations.sort(key=lambda r: (r["price"], r["dish"]))

    result: dict[str, Any] = {
        "query": query,
        "search_terms_used": tokens,
        "vegetarian_only": vegetarian_only,
        "budget": budget,
        "count": len(recommendations),
        "recommendations": recommendations,
        "notice": (
            "Fictional sample data. Budget applies to the listed dish "
            "price only, not delivery fees, taxes or other charges."
        ),
    }
    if errors:
        result["partial_results"] = True
        result["platform_errors"] = errors
        result["warning"] = (
            "Some platforms could not be reached; results are incomplete: "
            + ", ".join(errors)
        )
    return result


if __name__ == "__main__":
    mcp.run(transport="streamable-http")