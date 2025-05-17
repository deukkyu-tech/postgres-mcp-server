import logging
import uvicorn
import argparse
import importlib.util
import os
import sys
from pathlib import Path
import threading

from starlette.routing import Route
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
from starlette.requests import Request

from mcp.server.sse import SseServerTransport
from src.auth.jwt_utils import JWTUtils
from starlette.responses import StreamingResponse

import time
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("gumcp-server")

# 프로젝트 루트 설정
project_root = Path(__file__).parent.parent.parent  # /app
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

# Dictionary to store servers
servers = {}

# Store user-specific SSE transports and server instances
user_session_transports = {}
user_server_instances = {}

# Prometheus metrics
active_connections = Gauge(
    "gumcp_active_connections", "Number of active SSE connections", ["server"]
)
connection_total = Counter(
    "gumcp_connection_total", "Total number of SSE connections", ["server"]
)

# Default metrics port
METRICS_PORT = 9091

# Initialize JWT utils
jwt_utils = JWTUtils()


class SessionTimeoutMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, timeout_seconds=3600):
        super().__init__(app)
        self.timeout_seconds = timeout_seconds
        self.session_timestamps = {}  # {session_key: last_active_time}

    async def dispatch(self, request, call_next):
        # Skip authentication for metrics, root, health check, and token endpoints
        if request.url.path in ["/metrics", "/", "/health_check", "/token"]:
            return await call_next(request)
        session_key = None
        # logger.info(f"Entering dispatch for URL={request.url.path}, method={request.method}, params= {request.path_params}")
        server_name = request.url.path.split("/")[1]
        session_param = request.url.path.split("/")[2]
        session_key = f"{server_name}:{session_param}"
        self.session_timestamps[session_key] = time.time()
        response = await call_next(request)

        # Update timestamp on message receipt for POST requests to /messages/
        if request.method == "POST" and request.url.path.endswith("/messages/"):
            if session_key in self.session_timestamps:
                self.session_timestamps[session_key] = time.time()

        # Start cleanup task only once
        if session_key and not hasattr(self, "cleanup_task_started"):
            self.cleanup_task_started = True
            asyncio.create_task(self.cleanup_task())

        return response

    async def cleanup_task(self):
        while True:
            current_time = time.time()
            expired_sessions = [
                key
                for key, ts in self.session_timestamps.items()
                if current_time - ts > self.timeout_seconds
            ]
            for key in expired_sessions:
                if key in user_session_transports:
                    transport = user_session_transports.pop(key)
                    if key in user_server_instances:
                        del user_server_instances[key]
                    active_connections.labels(server=key.split(":")[0]).dec()
                    logger.info(f"Cleaned up idle session: {key}")
                    del self.session_timestamps[key]
            await asyncio.sleep(300)  # Check every minute


class JWTMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Skip authentication for metrics, root, health check, and token endpoints
        if request.url.path in ["/metrics", "/", "/health_check", "/token"]:
            return await call_next(request)

        # Check for Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"error": "Missing or invalid Authorization header"}, status_code=401
            )

        # Extract and verify JWT token
        token = auth_header[len("Bearer ") :]
        try:
            payload = jwt_utils.verify_jwt_token(token)
            request.state.user_id = payload["user_id"]
            request.state.conn_id = None
        except ValueError as e:
            logger.error(f"JWT verification failed: {e}")
            return JSONResponse({"error": str(e)}, status_code=401)

        return await call_next(request)


def discover_servers():
    """Discover and load all servers from the servers directory"""
    servers_dir = Path(__file__).parent.absolute()
    logger.info(f"Looking for servers in {servers_dir}")

    for item in servers_dir.iterdir():
        if item.is_dir():
            server_name = item.name
            server_file = item / "main.py"

            if server_file.exists():
                try:
                    spec = importlib.util.spec_from_file_location(
                        f"{server_name}.server", server_file
                    )
                    server_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(server_module)

                    if hasattr(server_module, "server") and hasattr(
                        server_module, "get_initialization_options"
                    ):
                        server = server_module.server
                        get_init_options = server_module.get_initialization_options
                        servers[server_name] = {
                            "server": server,
                            "get_initialization_options": get_init_options,
                        }
                        logger.info(f"Loaded server: {server_name}")
                    else:
                        logger.warning(
                            f"Server {server_name} does not have required server or get_initialization_options"
                        )
                except Exception as e:
                    logger.error(f"Failed to load server {server_name}: {e}")

    logger.info(f"Discovered {len(servers)} servers")


def create_metrics_app():
    """Create a separate Starlette app just for metrics"""

    async def metrics_endpoint(request):
        """Prometheus metrics endpoint"""
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    routes = [Route("/metrics", endpoint=metrics_endpoint)]
    app = Starlette(debug=True, routes=routes)
    return app


def create_starlette_app():
    """Create a Starlette app with multiple SSE transports for different servers"""
    discover_servers()
    routes = []

    async def token_endpoint(request: Request):
        """Issue a JWT token for the given user_id"""
        try:
            body = await request.json()
            user_id = body.get("user_id")

            if not user_id:
                return JSONResponse({"error": "user_id is required"}, status_code=400)

            jwt_token = jwt_utils.generate_jwt_token(user_id)
            logger.info(f"Issued JWT token for user {user_id} ")
            return JSONResponse({"success": True, "jwt_token": jwt_token})
        except ValueError as e:
            logger.error(f"Failed to issue JWT token: {e}")
            return JSONResponse({"error": str(e)}, status_code=400)
        except Exception as e:
            logger.error(f"Failed to issue JWT token: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    routes.append(Route("/token", endpoint=token_endpoint, methods=["POST"]))

    for server_name, server_info in servers.items():

        def create_handler(server_name, server_factory, get_init_options):
            async def handle_sse(request):
                """Handle SSE connection requests for a specific server and session"""
                session_key_encoded = request.path_params["session_key"]
                session_key = f"{server_name}:{session_key_encoded}"

                # Use user_id from JWT payload, conn_id from path if needed
                user_id = request.state.user_id
                # Parse conn_id from session_key if needed (e.g., user123:hash1)
                conn_id = (
                    session_key_encoded.split(":")[-1]
                    if ":" in session_key_encoded
                    else None
                )

                sse_transport = SseServerTransport(
                    f"/{server_name}/{session_key_encoded}/messages/"
                )

                user_session_transports[session_key] = sse_transport

                if session_key not in user_server_instances:
                    server_instance = server_factory(user_id, conn_id)
                    user_server_instances[session_key] = server_instance
                    active_connections.labels(server=server_name).inc()
                else:
                    server_instance = user_server_instances[session_key]

                init_options = get_init_options(server_instance)

                try:
                    # Always increment total connections counter
                    # connection_total.labels(server=server_name).inc()

                    async with sse_transport.connect_sse(
                        request.scope, request.receive, request._send
                    ) as streams:
                        logger.info(
                            f"SSE connection established for {server_name} session: {user_id}"
                        )
                        await server_instance.run(
                            streams[0],
                            streams[1],
                            init_options,
                        )
                finally:
                    if session_key in user_session_transports:
                        del user_session_transports[session_key]
                        # Decrement active connections metric
                        active_connections.labels(server=server_name).dec()
                        logger.info(
                            f"Closed SSE connection for {server_name} session: {user_id}"
                        )

            return handle_sse

        handler = create_handler(
            server_name,
            server_info["server"],
            server_info["get_initialization_options"],
        )
        routes.append(Route(f"/{server_name}/{{session_key}}", endpoint=handler))

        def create_message_handler(server_name):
            async def handle_message(request):
                """Handle messages sent to a specific user session"""
                session_key_encoded = request.path_params["session_key"]
                session_key = f"{server_name}:{session_key_encoded}"

                if session_key not in user_session_transports:
                    return Response(
                        f"Session not found or expired",
                        status_code=404,
                    )

                transport = user_session_transports[session_key]
                return transport.handle_post_message

            return handle_message

        message_handler = create_message_handler(server_name)
        routes.append(
            Route(
                f"/{server_name}/{{session_key}}/messages/",
                endpoint=message_handler,
                methods=["POST"],
            )
        )

        logger.info(f"Added user-specific routes for server: {server_name}")

    async def root_handler(request):
        """Root endpoint that returns a simple 200 OK response"""
        return JSONResponse(
            {
                "status": "ok",
                "message": "guMCP server running",
                "servers": list(servers.keys()),
            }
        )

    routes.append(Route("/", endpoint=root_handler))

    async def health_check(request):
        """Health check endpoint"""
        return JSONResponse({"status": "ok", "servers": list(servers.keys())})

    routes.append(Route("/health_check", endpoint=health_check))

    app = Starlette(debug=True, routes=routes)

    app.add_middleware(
        SessionTimeoutMiddleware, timeout_seconds=3600
    )  # Add session timeout middleware
    app.add_middleware(JWTMiddleware)  # Add JWT middleware

    return app


def run_metrics_server(host, port):
    """Run a separate metrics server on the specified port"""
    metrics_app = create_metrics_app()
    logger.info(f"Starting metrics server on {host}:{port}")
    uvicorn.run(metrics_app, host=host, port=port)


def main():
    """Main entry point for the Starlette server"""
    parser = argparse.ArgumentParser(description="guMCP Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host for Starlette server")
    parser.add_argument(
        "--port", type=int, default=8000, help="Port for Starlette server"
    )

    args = parser.parse_args()

    metrics_thread = threading.Thread(
        target=run_metrics_server, args=(args.host, METRICS_PORT), daemon=True
    )
    metrics_thread.start()
    logger.info(f"Starting Metrics server on http://{args.host}:{METRICS_PORT}/metrics")

    app = create_starlette_app()
    logger.info(f"Starting Starlette server on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
