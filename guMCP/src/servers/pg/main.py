import logging
import json
import asyncio
import decimal
import datetime
import uuid
from pathlib import Path
from enum import Enum
from typing import Optional
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.types import TextContent, Tool
from .database import Database

def safe_json_serializer(obj):
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    elif isinstance(obj, decimal.Decimal):
        return str(obj)
    elif isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
        return obj.isoformat()
    elif isinstance(obj, uuid.UUID):
        return str(obj)
    elif isinstance(obj, Path):
        return str(obj)
    elif isinstance(obj, bytes):
        return obj.decode('utf-8', errors='replace')
    elif isinstance(obj, set):
        return list(obj)
    elif isinstance(obj, Enum):
        return {"__enum__": f"{obj.__class__.__name__}.{obj.name}"}
    elif hasattr(obj, "__dict__"):
        return obj.__dict__
    else:
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

# Configure logging
SERVICE_NAME = Path(__file__).parent.name
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(SERVICE_NAME)

# Initialize global database
CONFIG_PATH = Path("/app/etc/config/pg_connections.json")
global_db = Database(config_path=CONFIG_PATH)
logger.info("Global database manager initialized")

def create_server(user_id: str, conn_id: Optional[str] = None) -> Server:
    server = Server("pg-server")
    server.user_id = user_id
    server.conn_id = conn_id

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
            List of TextContent objects containing a JSON string with:
            - success: True/False indicating query execution status
            - data: query results as a list of dictionaries (if success)
            - error: error message (if failure)
        """
        
        if not global_db:
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {"success": False, "error": "Database connection not available in MCP state"},
                        indent=2,
                        default=safe_json_serializer
                    )
                )
            ]
            
        logger.info(f"Executing query on connection ID {conn_id}: {query}")

        async with global_db.get_connection(conn_id) as conn:
            # Ensure we're in read-only mode
            await conn.execute("SET TRANSACTION READ ONLY")
            # Execute the query
            try:
                records = await conn.fetch(query, *(params or []))
                query_result = [dict(record) for record in records]
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {"success": True, "data": query_result},
                            indent=2,
                            default=safe_json_serializer
                        )
                    )
                ]
            except Exception as e:
                logger.error(f"Query execution error: {e}")
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {"success": False, "error": str(e)},
                            indent=2,
                            default=safe_json_serializer
                        )
                    )
                ]        
    @server.list_tools()
    async def handle_list_tools() -> list:
        return [
                Tool(
                    name="pg_connect",
                    description="Initialize a connection to a PostgreSQL database using the pre-configured connection ID",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "description": "No input parameters required as the connection ID is managed by the server",
                    },
                ),
                Tool(
                    name="pg_disconnect",
                    description="Close the connection to a PostgreSQL database using the pre-configured connection ID",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "description": "No input parameters required as the connection ID is managed by the server",
                    },
                ),
                Tool(
                    name="pg_query",
                    description="Execute a read-only SQL query against a PostgreSQL database",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "SQL query to execute (must be read-only, e.g., SELECT statements)",
                            },
                            "params": {
                                "type": "array",
                                "items": {"type": ["string", "number", "boolean", "null"]},
                                "description": "Optional parameters for the SQL query",
                                "default": [],
                            },
                        },
                        "required": ["query"],
                    },
                ),
                Tool(
                    name="pg_list_schemas",
                    description="List all schemas the current user has USAGE privilege on in the PostgreSQL database",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "description": "No input parameters required as this tool uses the current user's privileges",
                    },
                ),
                Tool(
                    name="pg_list_tables",
                    description="List all tables in a given schema that the current user has SELECT privilege on in the PostgreSQL database",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "schema": {
                                "type": "string",
                                "description": "Name of the schema to list tables from. Defaults to 'inst1' if not provided.",
                                "default": "inst1"
                            }
                        },
                        "required": [],
                        "description": "Schema name is optional; defaults to 'inst1'",
                    },
                ),
                Tool(
                    name="pg_list_table_metadata",
                    description="Get metadata (name, type, comment) of a specific table in a given schema in the PostgreSQL database, if the current user has SELECT privilege",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "schema": {
                                "type": "string",
                                "description": "Name of the schema where the table is located. Defaults to 'inst1' if not provided.",
                                "default": "inst1"
                            },
                            "table_name": {
                                "type": "string",
                                "description": "Name of the table to retrieve metadata for."
                            }
                        },
                        "required": ["table_name"],
                        "description": "Returns table metadata (name, type, comment) for a specific table in a schema",
                    },
                ),
                Tool(
                    name="pg_list_columns_metadata",
                    description="Get metadata for all columns of a specific table in a given schema in the PostgreSQL database",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "schema": {
                                "type": "string",
                                "description": "Name of the schema where the table is located. Defaults to 'inst1' if not provided.",
                                "default": "inst1"
                            },
                            "table_name": {
                                "type": "string",
                                "description": "Name of the table to retrieve column metadata for."
                            }
                        },
                        "required": ["table_name"],
                        "description": "Returns column metadata (name, type, length, nullability, default, comment) for a table in the given schema",
                    },
                ),
                Tool(
                    name="pg_count_table_rows",
                    description="Get the number of rows in a specific table within a given schema in the PostgreSQL database",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "schema": {
                                "type": "string",
                                "description": "Name of the schema where the table is located. Defaults to 'inst1' if not provided.",
                                "default": "inst1"
                            },
                            "table_name": {
                                "type": "string",
                                "description": "Name of the table to count rows from."
                            }
                        },
                        "required": ["table_name"],
                        "description": "Returns the total number of rows in the specified table within the given schema",
                    },
                ),
                Tool(
                    name="pg_sample_table_rows",
                    description="Retrieve sample 3 rows from a specific table in a given schema in the PostgreSQL database",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "schema": {
                                "type": "string",
                                "description": "Name of the schema where the table is located. Defaults to 'inst1' if not provided.",
                                "default": "inst1"
                            },
                            "table_name": {
                                "type": "string",
                                "description": "Name of the table to retrieve sample rows from."
                            }
                        },
                        "required": ["table_name"],
                        "description": "Returns the first 3 rows from the specified table in the given schema.",
                    },
                ),
            ]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent]:
        logger.info(f"User {server.user_id} calling tool: {name} with arguments: {arguments}")
        if arguments is None:
            arguments = {}

        # Restrict database-related tools if conn_id is not provided
        if not server.conn_id:
            return [TextContent(type="text", text=json.dumps({"success": False, "error": "conn_id is required for database operations"}))]
        try:
            match name:
                case "pg_connect":
                    try:                  
                        if server.conn_id not in global_db._connection_map:
                            return [TextContent(type="text", text=json.dumps({"success": False, "error": "Unknown connection ID"}))]
                        if server.conn_id not in global_db._pools:
                            try:
                                await global_db.initialize(server.conn_id)
                                return [TextContent(type="text", text=json.dumps({"success": True}))]
                            except Exception as e:
                                logger.error(f"Failed to initialize pool for connection ID {conn_id}: {e}")
                                return [TextContent(type="text", text=json.dumps({"success": False, "error": "Failed to initialize pool for connection ID"}))]
                    except Exception as e:
                        logger.error(f"Failed to pg_connect {conn_id}: {e}")
                        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

                case "pg_disconnect":
                    try:
                        if server.conn_id not in global_db._pools:
                            return [TextContent(type="text", text=json.dumps({"success": False, "error": "Unknown connection ID"}))]
                        try:
                            await global_db._pools[server.conn_id].close()
                            del global_db._pools[server.conn_id]
                            logger.info(f"Successfully disconnected and removed database connection pool with ID: {server.conn_id}")
                            return [TextContent(type="text", text=json.dumps({"success": True}))]
                        except Exception as e:
                            logger.error(f"Error disconnecting connection {server.conn_id}: {e}")
                            return [TextContent(type="text", text=json.dumps({"success": False, "error": "Error disconnecting connection"}))]
                    except Exception as e:
                        logger.error(f"Failed to pg_connect {server.conn_id}: {e}")
                        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))] 

                case "pg_query":
                    if "query" not in arguments:
                        return [TextContent(type="text", text=json.dumps({"success": False, "error": "SQL(postgreSQL) query is required"}))]
                    query = arguments["query"]
                    params = arguments.get("params",None)
                    # params가 단일 값이면 리스트로 변환
                    if params is not None and not isinstance(params, (list, tuple)):
                        params = [params]
                    # Execute the query using the connection ID 
                    return await execute_query(query, server.conn_id, params)

                case "pg_list_schemas":
                    query = """
                    SELECT schema_name
                    FROM information_schema.schemata
                    WHERE schema_name IN (
                        SELECT nspname
                        FROM pg_namespace
                        WHERE has_schema_privilege(nspname, 'USAGE')
                    )
                    ORDER BY schema_name;                   
                    """
                    # Execute the query using the connection ID 
                    return await execute_query(query, server.conn_id, None)
                case "pg_list_tables":
                    schema = arguments.get("schema", "public")
                    query = """
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = $1
                        AND has_table_privilege(table_schema || '.' || table_name, 'SELECT')
                        ORDER BY table_name;
                    """
                    params = [schema]
                    return await execute_query(query, server.conn_id, params)

                case "pg_list_table_metadata":
                    schema = arguments.get("schema", "public")
                    table_name = arguments.get("table_name")
                    query = """
                        SELECT table_name,
                            table_type,
                            obj_description(('"' || table_schema || '"."' || table_name || '"')::regclass, 'pg_class') AS table_comment
                        FROM information_schema.tables
                        WHERE table_schema = $1
                        AND table_name = $2
                        AND has_table_privilege(table_schema || '.' || table_name, 'SELECT')
                        ORDER BY table_name;
                    """
                    params = [schema, table_name]
                    return await execute_query(query, server.conn_id, params)

                case "pg_list_columns_metadata":
                    schema = arguments.get("schema", "public")
                    table_name = arguments["table_name"]  # 필수

                    query = """
                        SELECT 
                            column_name,
                            data_type,
                            character_maximum_length,
                            numeric_precision,
                            numeric_scale,
                            is_nullable,
                            column_default,
                            col_description(('"' || table_schema || '"."' || table_name || '"')::regclass, ordinal_position) AS column_comment
                        FROM information_schema.columns
                        WHERE table_schema = $1
                        AND table_name = $2
                        ORDER BY ordinal_position;
                    """
                    params = [schema, table_name]
                    return await execute_query(query, server.conn_id, params) 

                case "pg_count_table_rows":
                    schema = arguments.get("schema", "public")
                    table_name = arguments["table_name"]  # 필수

                    query = f"""
                        SELECT COUNT(*) AS row_count
                        FROM "{schema}"."{table_name}";
                    """
                    return await execute_query(query, server.conn_id)

                case "pg_sample_table_rows":
                    schema = arguments.get("schema", "public")
                    table_name = arguments["table_name"]  # 필수

                    query = f"""
                        SELECT * FROM "{schema}"."{table_name}" LIMIT 3;
                    """
                    return await execute_query(query, server.conn_id)
                case _:
                    return [TextContent(type="text", text=f"Unknown tool: {name}")]
        except Exception as e:
            logger.error(f"Error calling tool {name} for user {server.user_id}: {e}")
            return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

    asyncio.create_task(global_db.start_background_refresh())
    return server

server = create_server

def get_initialization_options(server_instance: Server) -> InitializationOptions:
    return InitializationOptions(
        server_name="pg-server",
        server_version="1.0.0",
        capabilities=server_instance.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={}
        )
    )