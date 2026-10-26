
# Food Recommendation MCP - Step 1

A local mock food-discovery MCP server for testing with compatible
MCP clients and the Kore.ai Artemis platform.

## Requirements

- Python 3.11 or a compatible Python version
- Internet access for installing the dependency
- Node.js/npm for the optional MCP Inspector

## Setup on Windows PowerShell

Open PowerShell in the project folder.

Create a virtual environment:

    py -3.11 -m venv .venv

Activate it:

    .\.venv\Scripts\Activate.ps1

If PowerShell blocks activation, run this in the current terminal:

    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

Then activate again:

    .\.venv\Scripts\Activate.ps1

Install dependencies:

    python -m pip install --upgrade pip
    pip install -r requirements.txt

Start the server:

    python swiggy_server.py

The MCP endpoint should be:

    http://127.0.0.1:8001/mcp

Keep this terminal running.

## Test with MCP Inspector

Open a second terminal and run:

    npx -y @modelcontextprotocol/inspector

Select Streamable HTTP as the transport and enter:

    http://127.0.0.1:8001/mcp

Connect and test the tools.

## Example tool inputs

search_restaurants:

    {
      "query": "biryani"
    }

get_restaurant_menu:

    {
      "restaurant_id": "sw_rest_001"
    }

search_menu_items:

    {
      "query": "biryani",
      "max_price": 250,
      "vegetarian_only": false
    }

get_available_offers:

    {}

## Notes

- All restaurant, menu, price, and offer data is fictional.
- This server supports food discovery only.
- It does not place orders, manage carts, or track deliveries.
- The server binds to localhost for local development.
- Verify Artemis's supported MCP transport and connectivity before
  configuring the integration. A localhost endpoint is not directly
  reachable by a cloud-hosted Artemis environment without an approved
  network-accessible deployment or tunnel.
