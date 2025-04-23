FROM mcp-server:latest
RUN pip install --no-cache-dir aiofiles
RUN pip install --no-cache-dir aiohttp