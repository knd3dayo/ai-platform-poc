import asyncio, os
import argparse
from fastmcp import FastMCP
from typing import Annotated

def hello(name: Annotated[str, "Your name"]) -> Annotated[str, "Greeting message"]:
    """
    A simple function that takes a name and returns a greeting message.
    Args:
        name (str): The name of the person to greet.
    Returns:
        str: A greeting message.
    """
    return f"Hello, {name}!"


async def main():
    mcp = FastMCP() 
    mcp.tool(hello)
    
    # port番号を取得
    port = 5001
    await mcp.run_async(transport="streamable-http", host="0.0.0.0", port=port)


if __name__ == "__main__":
    asyncio.run(main())
