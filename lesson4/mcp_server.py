"""A local MCP server exposing the same deterministic demo tools over stdio."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from tool_demo import calculate, get_weather


mcp = FastMCP("lesson4-demo")


@mcp.tool()
def weather(city: str) -> dict:
    """Get sample weather for Beijing, Shanghai, or Shenzhen."""
    return get_weather(city)


@mcp.tool()
def calculator(expression: str) -> dict:
    """Calculate an expression containing numbers and +, -, *, or /."""
    return calculate(expression)


if __name__ == "__main__":
    mcp.run(transport="stdio")

