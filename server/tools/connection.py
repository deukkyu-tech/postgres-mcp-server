from config import mcp
from mcp.server.fastmcp.utilities.logging import get_logger

logger = get_logger("pg-mcp.tools.connection")


def register_connection_tools():
    """Register the database connection tools with the MCP server."""
    logger.debug("Registering database connection tools")

    @mcp.tool()
    async def connect(conn_id: str):
        """
        Initialize a database connection and create a connection pool for the given connection ID.

        Args:
            conn_id: SHA-1 hash of the connection string

        Returns:
            Dictionary with connection initialization result
        """
        db = mcp.state["db"]

        # Ensure the connection pool is initialized for the given connection ID
        if conn_id not in db._pools:
            try:
                await db.initialize(conn_id)
            except Exception as e:
                logger.error(f"Failed to initialize pool for connection ID {conn_id}: {e}")
                return {"success": False, "error": f"Failed to initialize connection pool: {str(e)}"}

        # Check if the connection ID exists in the connection map
        if conn_id in db._connection_map:
            return {"success": True}
        else:
            logger.warning(f"Invalid connection ID: {conn_id}")
            return {"success": False, "error": "Unknown connection ID"}

    @mcp.tool()
    async def disconnect(conn_id: str):
        """
        Close a specific database connection and remove it from the pool.
        
        Args:
            conn_id: Connection ID to disconnect (required)
            
        Returns:
            Dictionary indicating success status
        """
        db = mcp.state["db"]
        
        # Check if the connection ID exists in the connection pool
        if conn_id not in db._pools:
            logger.warning(f"Attempted to disconnect unknown connection ID: {conn_id}")
            return {"success": False, "error": "Unknown connection ID"}
        
        # Proceed to close the connection pool and remove it
        try:
            # Close the connection pool for the given conn_id
            logger.info(f"Closing database connection pool for connection ID {conn_id}")
            await db._pools[conn_id].close()
            
            # Remove connection pool from the map
            del db._pools[conn_id]
            
            logger.info(f"Successfully disconnected and removed database connection pool with ID: {conn_id}")
            return {"success": True}
        
        except Exception as e:
            logger.error(f"Error disconnecting connection {conn_id}: {e}")
            return {"success": False, "error": str(e)}
