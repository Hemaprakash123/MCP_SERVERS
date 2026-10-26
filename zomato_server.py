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
    port=int(os.environ.get("PORT", "8002"))
)


def load_json(filename: str) -> list[dict[str, Any]]:
    path = DATA_DIR / filename

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_restaurants() -> list[dict[str, Any]]:
    return load_json("restaurants.json")


def load_menu() -> list[dict[str, Any]]:
    return load_json("zomato_menu_items.json")


@mcp.tool()
def search_restaurants(
    query: str = "",
    area: str = "",
    cuisine: str = "",
    min_rating: float = 0.0,
) -> dict[str, Any]:
    """Search mock Zomato restaurants by name, area, cuisine, and rating."""

    results = []

    for restaurant in load_restaurants():
        searchable_text = (
            restaurant["name"] + " "
            + " ".join(restaurant["cuisine"]) + " "
            + restaurant["area"]
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
        "platform": "mock_zomato",
        "count": len(results),
        "restaurants": results,
        "notice": "Fictional sample restaurant data.",
    }


@mcp.tool()
def get_restaurant_menu(restaurant_id: str) -> dict[str, Any]:
    """Get the mock Zomato menu for a restaurant ID."""

    restaurant = next(
        (
            r for r in load_restaurants()
            if r["id"] == restaurant_id
        ),
        None,
    )

    if restaurant is None:
        return {
            "platform": "mock_zomato",
            "error": f"Restaurant not found: {restaurant_id}",
        }

    items = [
        item for item in load_menu()
        if item["restaurant_id"] == restaurant_id
    ]

    return {
        "platform": "mock_zomato",
        "restaurant": restaurant,
        "count": len(items),
        "menu": items,
        "notice": "Menu prices are fictional test data.",
    }


@mcp.tool()
def search_menu_items(
    query: str = "",
    max_price: float = 0.0,
    vegetarian_only: bool = False,
) -> dict[str, Any]:
    """Search mock Zomato dishes by query, price, and vegetarian preference."""

    restaurants = {
        r["id"]: r["name"] for r in load_restaurants()
    }

    results = []

    for item in load_menu():
        searchable_text = (
            item["name"] + " "
            + item["category"] + " "
            + item["description"]
        ).lower()

        if query and query.lower() not in searchable_text:
            continue

        if max_price > 0 and item["price"] > max_price:
            continue

        if vegetarian_only and not item["is_vegetarian"]:
            continue

        results.append({
            **item,
            "restaurant_name": restaurants.get(
                item["restaurant_id"], "Unknown restaurant"
            ),
        })

    return {
        "platform": "mock_zomato",
        "count": len(results),
        "items": results,
    }


@mcp.tool()
def get_available_offers() -> dict[str, Any]:
    """Return fictional sample Zomato offers."""

    offers = load_json("zomato_offers.json")

    return {
        "platform": "mock_zomato",
        "count": len(offers),
        "offers": offers,
        "notice": "These are sample offers, not live promotions.",
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
