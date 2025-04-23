import json
import asyncpg
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from mcp.server.fastmcp.utilities.logging import get_logger
from hashlib import sha1
import aiofiles

logger = get_logger("pg-mcp.database")

class Database:
    def __init__(self, config_path="/etc/config/pg_connections.json"):
        self._pools = {}
        self._connection_map = {}  # { conn_id (sha1) : connection_string }
        self._config_path = Path(config_path)
        self._last_config_hash = None
        self._refresh_task = None

    async def start_background_refresh(self):
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = asyncio.create_task(self._refresh_loop())

    async def _refresh_loop(self):
        while True:
            try:
                await self._reload_config_if_changed()
            except Exception as e:
                logger.error(f"Error during config refresh: {e}")
            await asyncio.sleep(60)

    def _hash_config(self, content):
        return sha1(json.dumps(content, sort_keys=True).encode()).hexdigest()

    async def _reload_config_if_changed(self):
        if not self._config_path.exists():
            logger.warning(f"Config path {self._config_path} not found.")
            return

        # 비동기적으로 파일을 읽음
        async with aiofiles.open(self._config_path, mode='r') as f:
            content = await f.read()
            content = json.loads(content)

        current_hash = self._hash_config(content)
        if current_hash == self._last_config_hash:
            return

        logger.info("Detected config map change, updating connections")
        self._last_config_hash = current_hash

        self._connection_map = content  # key = sha1, value = connection string

    def get_connection_string(self, conn_id):
        if conn_id not in self._connection_map:
            raise ValueError(f"Unknown connection ID: {conn_id}")
        return self._connection_map[conn_id]

    async def initialize(self, conn_id):
        if not conn_id:
            raise ValueError("Connection ID is required")

        if conn_id not in self._pools:
            conn_str = self.get_connection_string(conn_id)

            logger.info(f"Creating new database connection pool for connection ID {conn_id}")
            self._pools[conn_id] = await asyncpg.create_pool(
                conn_str,
                min_size=2,
                max_size=4,
                command_timeout=60.0,
                server_settings={"default_transaction_read_only": "true"}
            )
        return self

    @asynccontextmanager
    async def get_connection(self, conn_id):
        if conn_id not in self._pools:
            await self.initialize(conn_id)

        async with self._pools[conn_id].acquire() as conn:
            yield conn

    async def close(self, conn_id=None):
        if conn_id:
            if conn_id in self._pools:
                logger.info(f"Closing database connection pool for connection ID {conn_id}")
                await self._pools[conn_id].close()
                del self._pools[conn_id]
        else:
            logger.info("Closing all database connection pools")
            for id, pool in list(self._pools.items()):
                logger.info(f"Closing connection pool for ID {id}")
                await pool.close()
                del self._pools[id]
