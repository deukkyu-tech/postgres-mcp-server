FROM python:3.13-slim

RUN apt-get clean \
    && apt-get -y update

RUN apt-get install -y vim
RUN apt-get install -y --no-install-recommends curl
RUN apt-get install -y --no-install-recommends ca-certificates

RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir dotenv
RUN pip install --no-cache-dir grpcio
RUN pip install --no-cache-dir httpx
RUN pip install --no-cache-dir mcp
RUN pip install --no-cache-dir fastmcp
RUN pip install --no-cache-dir langchain
RUN pip install --no-cache-dir langchain-openai
RUN pip install --no-cache-dir langchain_mcp_adapters
RUN pip install --no-cache-dir langgraph
RUN pip install --no-cache-dir uv
RUN pip install --no-cache-dir asyncpg
RUN pip install --no-cache-dir trino
RUN pip install --no-cache-dir streamlit
RUN pip install --no-cache-dir notebook jupyterlab
RUN pip install --no-cache-dir langchain-groq
RUN pip install --no-cache-dir nest_asyncio

ENV TZ=Asia/Seoul

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ

RUN mkdir -p /app
WORKDIR /app

CMD ["/bin/bash"]
