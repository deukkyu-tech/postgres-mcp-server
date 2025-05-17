import argparse
import traceback
import json
from typing import Optional, List, Dict, Any
from contextlib import AsyncExitStack
from openai import OpenAI
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.sse import sse_client
import os
import asyncio
import httpx

load_dotenv()

class RemoteMCPTestClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, token: Optional[str] = None):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.token = token
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key not provided")
        # 동기 OpenAI 클라이언트 초기화
        self.openai = OpenAI(api_key=api_key, base_url=base_url or "https://api.openai.com/v1")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()

    async def connect_to_server(self, sse_endpoint: str):
        """SSE를 통해 원격 MCP 서버에 연결"""
        print(f"Connecting to server at {sse_endpoint}")
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

        # 비동기 컨텍스트로 SSE 스트림과 세션 초기화
        read_stream, write_stream = await self.exit_stack.enter_async_context(
            sse_client(sse_endpoint, headers=headers)
        )
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )

        print("Initializing Client Session...")
        await self.session.initialize()
        print("Session initialized!")

        print("Listing tools...")
        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools:", [tool.name for tool in tools])

    async def list_resources(self) -> None:
        """서버에서 사용 가능한 리소스 목록 조회"""
        if not self.session:
            raise ValueError("Session not initialized")
        try:
            return await self.session.list_resources()
        except Exception as e:
            print(f"Error listing resources: {e}")
            traceback.print_exc()

    async def read_resource(self, uri: str) -> None:
        """특정 리소스 읽기"""
        if not self.session:
            raise ValueError("Session not initialized")
        try:
            return await self.session.read_resource(uri)
        except Exception as e:
            print(f"Error reading resource: {e}")
            traceback.print_exc()

    async def process_query(self, query: str) -> str:
        """GPT-4o를 사용해 쿼리 처리 및 툴 호출"""
        messages: List[Dict[str, Any]] = [{"role": "user", "content": query}]

        if not self.session:
            raise ValueError("Session not initialized")

        # 사용 가능한 툴 목록 조회
        response = await self.session.list_tools()
        available_tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema
                }
            } for tool in response.tools
        ]

        # GPT-4o 초기 호출 (동기 API 사용)
        response = self.openai.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=available_tools,
            tool_choice="auto"
        )
        final_text = []
        choice = response.choices[0]

        if choice.message.content:
            final_text.append(choice.message.content)

        if choice.message.tool_calls:
            for tool_call in choice.message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                # 툴 호출 실행
                result = await self.session.call_tool(tool_name, tool_args)
                final_text.append(f"[Called tool {tool_name} with args {tool_args}]")

                # assistant 역할로 tool_call 명시
                messages.append({
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(tool_args)
                            }
                        }
                    ]
                })

                # tool 역할로 응답 추가
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": "\n".join(content.text for content in result.content)
                })
                
                # 후속 GPT-4o 호출
                try:
                    response = self.openai.chat.completions.create(
                        model="gpt-4o",
                        messages=messages,
                        tools=available_tools,
                        tool_choice="auto"
                    )
                except Exception as e:
                    print("후속 GPT-4o 호출 에러:", e)
                    raise
                followup_choice = response.choices[0]
                if followup_choice.message.content:
                    final_text.append(followup_choice.message.content)

        return "\n".join(final_text)

    async def chat_loop(self):
        """대화형 쿼리 처리 루프"""
        print("\nRemote MCP Client Started!")
        print("Type your queries or 'quit' to exit.")
        while True:
            try:
                query = input("\nQuery: ").strip()
                if query.lower() == "quit":
                    break
                response = await self.process_query(query)
                print("\n" + response)
            except Exception as e:
                print(f"\nError: {str(e)}")
                traceback.print_exc()

    async def cleanup(self):
        try:
            if self.session:
                # ClientSession 정리
                try:
                    # 명시적 종료 메서드 확인
                    if hasattr(self.session, "close"):
                        await self.session.close()
                    elif hasattr(self.session, "shutdown"):
                        await self.session.shutdown()
                    elif hasattr(self.session, "disconnect"):
                        await self.session.disconnect()
                except Exception as e:
                    print(f"Error closing session: {e}")
                finally:
                    self.session = None

            # AsyncExitStack 정리
            try:
                # _exit_callbacks를 안전하게 처리
                while self.exit_stack._exit_callbacks:
                    cm = self.exit_stack._exit_callbacks.pop()
                    try:
                        # cm이 callable인지 확인
                        if callable(cm):
                            await cm(None, None, None)
                        # else:
                            # print(f"Skipping non-callable context manager: {cm}")
                    except Exception as e:
                        print(f"Error closing context manager: {e}")
            except Exception as e:
                print(f"Error during exit stack cleanup: {e}")
        finally:
            pass
            # print(f"Cleanup end in task: {id(asyncio.current_task())}")

    async def llm_as_a_judge(self, requirements: str, response: str) -> dict:
        """GPT-4o를 사용해 응답이 요구사항을 충족하는지 평가"""
        evaluation_prompt = f"""
        You are a judge evaluating if a response meets the given requirements.

        REQUIREMENTS:
        {requirements}

        RESPONSE TO EVALUATE:
        {response}

        Only return a JSON:
        {{
            "passed": true/false,
            "reasoning": "Concise reasoning"
        }}
        """
        messages = [{"role": "user", "content": evaluation_prompt.strip()}]

        gpt_response = self.openai.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=100
        )

        try:
            return json.loads(gpt_response.choices[0].message.content)
        except Exception:
            return {"passed": False, "reasoning": "Could not parse response as JSON"}

    async def fetch_value_from_response(self, response: str, schema: dict) -> dict:
        """응답에서 스키마에 따라 구조화된 데이터 추출"""
        schema_str = "\n".join([f"- {key}: {value}" for key, value in schema.items()])

        extraction_prompt = f"""
        Extract the following from the text below.

        TEXT:
        {response}

        INSTRUCTIONS:
        {schema_str}

        Return valid JSON. If a value is not found, set it to null.
        """
        messages = [{"role": "user", "content": extraction_prompt.strip()}]

        gpt_response = self.openai.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=300
        )

        try:
            return json.loads(gpt_response.choices[0].message.content)
        except Exception:
            return {key: None for key in schema.keys()}

async def main():
    parser = argparse.ArgumentParser(description="Remote MCP Test Client")
    parser.add_argument("--endpoint", default="http://localhost:8000/pg/test_user:test_key")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--base-url", default="https://api.openai.com/v1")
    args = parser.parse_args()

    # 동기 HTTP 클라이언트로 토큰 발급
    with httpx.Client() as http_client:
        response = http_client.post(
            "http://localhost:8000/token",
            json={"user_id": "test_user"}
        )
        response.raise_for_status()
        token = response.json()["jwt_token"]

    client = RemoteMCPTestClient(api_key=args.api_key, base_url=args.base_url, token=token)
    try:
        await client.connect_to_server(args.endpoint)
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    asyncio.run(main())