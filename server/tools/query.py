# server/tools/query.py
from config import mcp
from mcp.server.fastmcp import Context
from mcp.server.fastmcp.utilities.logging import get_logger

logger = get_logger("pg-mcp.tools.query")

async def execute_query(query: str, conn_id: str, params=None):
    """
    Execute a read-only SQL query against the PostgreSQL database.
    
    Args:
        query: The SQL query to execute (must be read-only)
            example) select * from table or select * from table where id = $1      
        conn_id: Connection ID (required)       
        params: Parameters for the query (optional)
            example) (5,'Alice')
        
    Returns:
        Query results as a list of dictionaries
    """
    

    db = mcp.state["db"]
    if not db:
        raise ValueError("Database connection not available in MCP state.")
        
    logger.info(f"Executing query on connection ID {conn_id}: {query}")
    
    async with db.get_connection(conn_id) as conn:
        # Ensure we're in read-only mode
        await conn.execute("SET TRANSACTION READ ONLY")
        
        # Execute the query
        try:
            records = await conn.fetch(query, *(params or []))
            return [dict(record) for record in records]
        except Exception as e:
            # Log the error but don't couple to specific error types
            logger.error(f"Query execution error: {e}")
            raise

def register_query_tools():
    """Register database query tools with the MCP server."""
    logger.debug("Registering query tools")
    
    @mcp.tool()
    async def pg_query(query: str, conn_id: str, params=None):
        """
        Execute a read-only SQL query against the PostgreSQL database.
        
        Args:
            query: The SQL query to execute (must be read-only)
            conn_id: Connection ID previously obtained from the connect tool
            params: Parameters for the query (optional)
            
        Returns:
            Query results as a list of dictionaries
        """
        # Execute the query using the connection ID 
        return await execute_query(query, conn_id, params)
        
    @mcp.tool()
    async def pg_explain(query: str, conn_id: str, params=None):
        """
        Execute an EXPLAIN (FORMAT JSON) query to get PostgreSQL execution plan.
        
        Args:
            query: The SQL query to analyze
            conn_id: Connection ID previously obtained from the connect tool
            params: Parameters for the query (optional)
            
        Returns:
            Complete JSON-formatted execution plan
        """
        # Prepend EXPLAIN to the query
        explain_query = f"EXPLAIN (FORMAT JSON) {query}"
        
        # Execute the explain query
        result = await execute_query(explain_query, conn_id, params)
        
        # Return the complete result
        return result