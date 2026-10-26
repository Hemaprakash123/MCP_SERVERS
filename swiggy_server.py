import os
import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

mcp = FastMCP(
    "Mock Swiggy Food Discovery",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8001"))
)


def load_json(filename: str) -> list[dict[str, Any]]:
    """Load sample data from the local JSON files."""
    path = DATA_DIR / filename

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


@mcp.tool()
def search_restaurants(
    query: str = "",
    area: str = "",
    cuisine: str = "",
    min_rating: float = 0.0,
) -> dict[str, Any]:
    """Search sample restaurants by name, area, cuisine, and minimum rating."""

    restaurants = load_json("restaurants.json")

    results = []

    for restaurant in restaurants:
        searchable_text = (
            restaurant["name"] + " " +
            " ".join(restaurant["cuisine"]) + " " +
            restaurant["area"]
        ).lower()

        if query and query.lower() not in searchable_text:
            continue

        if area and area.lower() not in restaurant["area"].lower():
            continue

        if cuisine and not any(
            cuisine.lower() in item.lower()
            for item in restaurant["cuisine"]
        ):
            continue

        if restaurant["rating"] < min_rating:
            continue

        results.append(restaurant)

    return {
        "platform": "mock_swiggy",
        "count": len(results),
        "restaurants": results,
    }


@mcp.tool()
def get_restaurant_menu(restaurant_id: str) -> dict[str, Any]:
    """Get all sample menu items for a restaurant ID."""

    restaurants = load_json("restaurants.json")
    menu_items = load_json("menu_items.json")

    restaurant = next(
        (r for r in restaurants if r["id"] == restaurant_id),
        None,
    )

    if restaurant is None:
        return {
            "platform": "mock_swiggy",
            "error": f"Restaurant not found: {restaurant_id}",
        }

    items = [
        item for item in menu_items
        if item["restaurant_id"] == restaurant_id
    ]

    return {
        "platform": "mock_swiggy",
        "restaurant": restaurant,
        "count": len(items),
        "menu": items,
    }


@mcp.tool()
def search_menu_items(
    query: str = "",
    max_price: float = 0.0,
    vegetarian_only: bool = False,
) -> dict[str, Any]:
    """Search dishes by name, category, maximum price, or vegetarian preference."""

    restaurants = load_json("restaurants.json")
    menu_items = load_json("menu_items.json")

    restaurant_lookup = {
        restaurant["id"]: restaurant["name"]
        for restaurant in restaurants
    }

    results = []

    for item in menu_items:
        searchable_text = (
            item["name"] + " " + item["category"] + " " +
            item["description"]
        ).lower()

        if query and query.lower() not in searchable_text:
            continue

        if max_price > 0 and item["price"] > max_price:
            continue

        if vegetarian_only and not item["is_vegetarian"]:
            continue

        results.append({
            **item,
            "restaurant_name": restaurant_lookup.get(
                item["restaurant_id"], "Unknown restaurant"
            ),
        })

    return {
        "platform": "mock_swiggy",
        "count": len(results),
        "items": results,
    }


@mcp.tool()
def get_available_offers() -> dict[str, Any]:
    """Get the fictional sample offers available on the mock platform."""

    offers = load_json("offers.json")

    return {
        "platform": "mock_swiggy",
        "count": len(offers),
        "offers": offers,
        "notice": "These are sample offers, not live promotions.",
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
