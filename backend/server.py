"""
Unified entry point — runs the FastAPI HTTP server and the MCP stdio server
in the same asyncio event loop so they share pending_store state.

Usage:
    python -m backend.server
"""
import asyncio
import uvicorn
from mcp.server.stdio import stdio_server

from backend.logging_config import setup_logging
from backend.main import app
from backend import mcp_server

setup_logging()


async def main():
    http = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=8000, log_config=None))
    async with stdio_server() as (read_stream, write_stream):
        await asyncio.gather(
            http.serve(),
            mcp_server.server.run(
                read_stream,
                write_stream,
                mcp_server.server.create_initialization_options(),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
