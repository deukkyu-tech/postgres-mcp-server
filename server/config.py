from mcp.server.fastmcp import FastMCP
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from database import Database
from mcp.server.fastmcp.utilities.logging import get_logger

from pathlib import Path  # ⬅ config 파일 경로를 지정하기 위해 필요
import asyncio  # ⬅ background task 실행을 위해 필요

logger = get_logger("pg-mcp.instance")

# ConfigMap 경로 지정 (예시: /etc/config/db-config.json)
CONFIG_PATH = Path("/app/etc/config/db-config.json")

# Global database instance 생성
global_db = Database(config_path=CONFIG_PATH)
logger.info("Global database manager initialized")


@asynccontextmanager
async def app_lifespan(app: FastMCP) -> AsyncIterator[dict]:
    """Manage application lifecycle."""
    mcp.state = {"db": global_db}
    logger.info("Application startup - using global database manager")

    # ConfigMap 변경 감지를 위한 background refresh 시작
    await global_db.start_background_refresh()

    try:
        yield {"db": global_db}
    finally:
        # Don't close connections on individual session end
        pass

# Create the MCP instance
mcp = FastMCP(
    "pg-mcp-server", 
    debug=True, 
    lifespan=app_lifespan,
    dependencies=["asyncpg", "mcp"]
)