import pytest
import json
from tests.utils.test_tools import get_test_id, run_tool_test

# TOOL_TESTS = [
#     {
#         "name": "pg_connect",
#         "args_template": "",
#         "expected_keywords": ["success"],
#         "regex_extractors": {"success": r'"success":\s*(true|false)'},
#         "description": "initialize a connection to a PostgreSQL database using the pre-configured connection ID",
#         "setup": lambda ctx: {
#                 "success": json.loads(ctx["success"]) if isinstance(ctx.get("success"), str) else ctx.get("success", False)
#             }
#     },
#     {
#         "name": "pg_list_schemas",
#         "args_template": "",
#         "expected_keywords": ["success", "data"],
#         "regex_extractors": {
#             "success": r'"success":\s*(true|false)',
#             "schemas_json": r'"data":\s*(\[[\s\S]*?\])'
#         },
#         "description": "list all schemas with USAGE privilege",
#         "depends_on": ["success"],
#         "setup": lambda ctx: {"schema": None} if not ctx.get("success") or not json.loads(ctx["success"]) else {
#             "schema": next(
#                 (item["schema_name"] for item in json.loads(ctx["schemas_json"]) if item["schema_name"] == "public"),
#                 None
#             )
#         }
#     },
#     {
#         "name": "pg_list_tables",
#         "args_template": 'with schema="{schema}"',
#         "expected_keywords": ["success", "data"],
#         "regex_extractors": {
#             "success": r'"success":\s*(true|false)',
#             "tables_json": r'"data":\s*(\[[\s\S]*?\])'
#         },
#         "description": "list tables in selected schema",
#         "depends_on": ["success", "schema"],
#         "setup": lambda ctx: {"table": None} if not ctx.get("success") or not json.loads(ctx["success"]) else {
#             "table": next(
#                 (item["table_name"] for item in json.loads(ctx["tables_json"]) if item["table_name"] == "customers"),
#                 None
#             )
#         }
#     },
#     {
#         "name": "pg_list_table_metadata",
#         "args_template": 'with schema={schema}, table_name={table}',
#         "expected_keywords": ["success", "data"],
#         "regex_extractors": {
#             "success": r'"success":\s*(true|false)',
#             "data": r'"data":\s*(\[[\s\S]*?\])'
#         },
#         "description": "Get metadata (name, type, comment) of a specific table in a given schema in the PostgreSQL database, if the current user has SELECT privilege",
#         "depends_on": ["success", "schema", "table"],
#     },
#     {
#         "name": "pg_list_columns_metadata",
#         "args_template": 'with schema={schema}, table_name={table}',
#         "expected_keywords": ["success", "data"],
#         "regex_extractors": {
#             "success": r'"success":\s*(true|false)',
#             "data": r'"data":\s*(\[[\s\S]*?\])'
#         },
#         "description": "Get metadata for all columns of a specific table in a given schema in the PostgreSQL database",
#         "depends_on": ["success", "schema", "table"],
#     },
#     {
#         "name": "pg_count_table_rows",
#         "args_template": 'with schema={schema}, table_name={table}',
#         "expected_keywords": ["success", "data"],
#         "regex_extractors": {
#             "success": r'"success":\s*(true|false)',
#             "data": r'"data":\s*(\[[\s\S]*?\])'
#         },
#         "description": "Get the number of rows in a specific table within a given schema in the PostgreSQL database",
#         "depends_on": ["success", "schema", "table"],
#     },     
#     {
#         "name": "pg_query",
#         "args_template": 'with query="SELECT * FROM {schema}.{table} LIMIT 5"',
#         "expected_keywords": ["success", "data"],
#         "regex_extractors": {
#             "success": r'"success":\s*(true|false)',
#             "data": r'"data":\s*(\[[\s\S]*?\])'
#         },
#         "description": "execute a SELECT query on the chosen table",
#         "depends_on": ["success", "schema", "table"],
#     },
#     {
#         "name": "pg_disconnect",
#         "args_template": "",
#         "expected_keywords": ["success"],
#         "regex_extractors": {"success": r'"success":\s*(true|false)'},
#         "description": "disconnect from the PostgreSQL database",
#         "depends_on": ["success"],  # pg_disconnect도 success에 의존
#     }
# ]



TOOL_TESTS = [
    {
        "name": "pg_connect",
        "args_template": "",
        "expected_keywords": ["success"],
        "regex_extractors": {"success": r'"success":\s*(true|false)'},
        "description": "initialize a connection to a PostgreSQL database using the pre-configured connection ID",
    },
    {
        "name": "pg_list_schemas",
        "args_template": "",
        "expected_keywords": ["success", "data"],
        "regex_extractors": {
            "success": r'"success":\s*(true|false)',
            "schemas_json": r'"data":\s*(\[[\s\S]*?\])'
        },
        "description": "list all schemas with USAGE privilege",
        "depends_on": ["success"],
        "setup": lambda ctx: {"schema": None} if not ctx.get("success") or not json.loads(ctx["success"]) else {
            "schema": next(
                (item["schema_name"] for item in json.loads(ctx["schemas_json"]) if item["schema_name"] == "public"),
                None
            )
        }
    },
    {
        "name": "pg_list_tables",
        "args_template": 'with schema="{schema}"',
        "expected_keywords": ["success", "data"],
        "regex_extractors": {
            "success": r'"success":\s*(true|false)',
            "tables_json": r'"data":\s*(\[[\s\S]*?\])'
        },
        "description": "list tables in selected schema",
        "depends_on": ["schema"],
        "setup": lambda ctx: {"table": None} if not ctx.get("success") or not json.loads(ctx["success"]) else {
            "table": next(
                (item["table_name"] for item in json.loads(ctx["tables_json"]) if item["table_name"] == "customers"),
                None
            )
        }
    },
    {
        "name": "pg_list_table_metadata",
        "args_template": 'with schema={schema}, table_name={table}',
        "expected_keywords": ["success", "data"],
        "description": "Get metadata (name, type, comment) of a specific table in a given schema in the PostgreSQL database, if the current user has SELECT privilege",
        "depends_on": ["schema", "table"],
    },
    {
        "name": "pg_list_columns_metadata",
        "args_template": 'with schema={schema}, table_name={table}',
        "expected_keywords": ["success", "data"],
        "description": "Get metadata for all columns of a specific table in a given schema in the PostgreSQL database",
        "depends_on": ["schema", "table"],
    },
    {
        "name": "pg_count_table_rows",
        "args_template": 'with schema={schema}, table_name={table}',
        "expected_keywords": ["success", "data"],
        "description": "Get the number of rows in a specific table within a given schema in the PostgreSQL database",
        "depends_on": ["schema", "table"],
    },    
    {
        "name": "pg_sample_table_rows",
        "args_template": 'with schema={schema}, table_name={table}',
        "expected_keywords": ["success", "data"],
        "description": "Retrieve sample 3 rows from a specific table in a given schema in the PostgreSQL database",
        "depends_on": ["schema", "table"],
    },   
    {
        "name": "pg_query",
        "args_template": 'with query="SELECT * FROM {schema}.{table} LIMIT 5"',
        "expected_keywords": ["success", "data"],
        "description": "execute a SELECT query on the chosen table",
        "depends_on": ["schema", "table"],
    },
    {
        "name": "pg_disconnect",
        "args_template": "",
        "expected_keywords": ["success"],
        "regex_extractors": {"success": r'"success":\s*(true|false)'},
        "description": "disconnect from the PostgreSQL database",
    }
]

# Shared context dictionary at module level
# SHARED_CONTEXT = {"success":False,"schemas_json":None,"tables_json":None,"data":None,"table":None,"schema":None}
SHARED_CONTEXT = {}

@pytest.fixture(scope="module")
def context():
    return SHARED_CONTEXT

@pytest.mark.parametrize("test_config", TOOL_TESTS, ids=get_test_id)
@pytest.mark.asyncio
async def test_pg_tool(client, context, test_config):
    return await run_tool_test(client, context, test_config)