
import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.server.fastmcp import FastMCP

SWIGGY_URL = "http://127.0.0.1:8001/mcp"
ZOMATO_URL = "http://127.0.0.1:8002/mcp"

mcp = FastMCP(
    "Food Price Comparison",
    host="127.0.0.1",
    port=8003,
)


async def call_remote_tool(
    server_url: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Connect to an MCP server and call one of its tools."""

    async with streamablehttp_client(server_url) as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            result = await session.call_tool(
                tool_name,
                arguments=arguments,
            )

            if result.isError:
                raise RuntimeError(
                    f"{tool_name} failed on {server_url}"
                )

            for content in result.content:
                if getattr(content, "text", None):
                    try:
                        return json.loads(content.text)
                    except json.JSONDecodeError:
                        continue

            raise RuntimeError(
                f"No JSON result returned by {tool_name}"
            )


async def search_both_platforms(
    query: str,
    max_price: float = 0,
    vegetarian_only: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Search Swiggy and Zomato concurrently."""

    arguments = {
        "query": query,
        "max_price": max_price,
        "vegetarian_only": vegetarian_only,
    }

    swiggy, zomato = await asyncio.gather(
        call_remote_tool(
            SWIGGY_URL,
            "search_menu_items",
            arguments,
        ),
        call_remote_tool(
            ZOMATO_URL,
            "search_menu_items",
            arguments,
        ),
    )

    return swiggy, zomato


@mcp.tool()
async def compare_menu_prices(
    query: str,
    max_price: float = 0,
    vegetarian_only: bool = False,
) -> dict[str, Any]:
    """Compare matching dishes and prices on Swiggy and Zomato.

    This compares listed menu prices only, not final checkout totals.
    """

    swiggy, zomato = await search_both_platforms(
        query,
        max_price,
        vegetarian_only,
    )

    swiggy_items = swiggy.get("items", [])
    zomato_items = zomato.get("items", [])

    zomato_by_id = {
        item["id"]: item for item in zomato_items
    }

    comparisons = []

    for sw_item in swiggy_items:
        zo_item = zomato_by_id.get(sw_item["id"])

        if not zo_item:
            continue

        sw_price = float(sw_item["price"])
        zo_price = float(zo_item["price"])

        if sw_price < zo_price:
            cheaper = "Swiggy"
        elif zo_price < sw_price:
            cheaper = "Zomato"
        else:
            cheaper = "Same price"

        comparisons.append({
            "dish": sw_item["name"],
            "restaurant": sw_item["restaurant_name"],
            "swiggy_price": sw_price,
            "zomato_price": zo_price,
            "difference_rupees": round(
                abs(sw_price - zo_price), 2
            ),
            "cheaper_platform": cheaper,
        })

    comparisons.sort(
        key=lambda item: min(
            item["swiggy_price"],
            item["zomato_price"],
        )
    )

    return {
        "query": query,
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
    query: str,
    budget: float,
    vegetarian_only: bool = False,
) -> dict[str, Any]:
    """Find matching dishes whose listed price fits the budget."""

    if budget <= 0:
        return {
            "error": "Budget must be greater than zero."
        }

    swiggy, zomato = await search_both_platforms(
        query=query,
        vegetarian_only=vegetarian_only,
    )

    recommendations = []

    for platform, response in [
        ("Swiggy", swiggy),
        ("Zomato", zomato),
    ]:
        for item in response.get("items", []):
            price = float(item["price"])

            if price <= budget:
                recommendations.append({
                    "platform": platform,
                    "dish": item["name"],
                    "restaurant": item["restaurant_name"],
                    "price": price,
                    "budget_remaining": round(
                        budget - price, 2
                    ),
                    "is_vegetarian": item["is_vegetarian"],
                })

    recommendations.sort(key=lambda item: item["price"])

    return {
        "query": query,
        "budget": budget,
        "count": len(recommendations),
        "recommendations": recommendations,
        "notice": (
            "Budget applies to the listed dish price only, "
            "not delivery fees, taxes or other charges."
        ),
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
