# server/app.py
from mcp.server.fastmcp.utilities.logging import configure_logging, get_logger
import logging
import sys

# Configure logging
configure_logging(level="DEBUG")
logger = get_logger("pg-mcp")

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
root_logger.addHandler(handler)

# Import mcp instance
from config import mcp, global_db

# Import registration functions
from tools.connection import register_connection_tools
from tools.query import register_query_tools

# Register tools and resources with the MCP server
register_connection_tools()  # Connection management tools
register_query_tools()

from contextlib import asynccontextmanager
from starlette.applications import Starlette
from starlette.routing import Mount
import uvicorn

@asynccontextmanager
async def starlette_lifespan(app):
    logger.info("Starlette application starting up")
    yield
    logger.info("Starlette application shutting down, closing all database connections")
    await global_db.close()

if __name__ == "__main__":
    logger.info("Starting MCP server with SSE transport")
    app = Starlette(routes=[Mount('/', app=mcp.sse_app())])
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")