import os
import pytest
import pytest_asyncio
from typing import List
import httpx
import asyncio
import anyio
from tests.clients.RemoteMCPTestClient import RemoteMCPTestClient

pytest_plugins = ["pytest_asyncio"]

def pytest_configure(config):
    config.option.asyncio_default_fixture_loop_scope = "function"

def pytest_addoption(parser):
    parser.addoption(
        "--remote",
        action="store_true",
        help="Run tests in remote mode",
    )
    parser.addoption(
        "--endpoint",
        action="store",
        default=None,
        help="URL for the remote server endpoint (for remote tests)",
    )

def pytest_collection_modifyitems(items: List[pytest.Item]):
    for item in items:
        if (
            item.get_closest_marker("asyncio") is None
            and "async def" in item.function.__code__.co_code
        ):
            item.add_marker(pytest.mark.asyncio)

@pytest_asyncio.fixture(scope="function")
async def client(request):
    test_path = request.node.fspath.strpath
    server_name = os.path.basename(os.path.dirname(test_path))
    endpoint = (
        request.config.getoption("--endpoint")
        or f"http://localhost:8000/{server_name}/test_user:test_key"
    )

    # 동기 HTTP 클라이언트로 토큰 발급
    with httpx.Client() as http_client:
        response = http_client.post(
            f"http://localhost:8000/token",
            json={"user_id": "test_user", "service_name": server_name}
        )
        response.raise_for_status()
        token = response.json()["jwt_token"]

    client = RemoteMCPTestClient(token=token)
    print(f"Client fixture setup in task: {asyncio.current_task()}")

    try:
        await client.connect_to_server(endpoint)
        print(f"Connected to {server_name} at {endpoint} with token")
        yield client
    finally:
        # print(f"Cleanup client in task: {id(asyncio.current_task())}")
        await client.cleanup()