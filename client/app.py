import streamlit as st
import asyncio
import nest_asyncio
import os
import time
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

# 중복 이벤트 루프 방지
nest_asyncio.apply()

# 환경 변수 로드
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")

# 제목
st.title("🧠 LangChain MCP Agent")

# 초기 세션 상태
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [
        SystemMessage(content="모든 응답은 한국어로 해 주세요.")
    ]

# 🔄 대화 초기화 버튼
if st.button("🔄 대화 초기화"):
    # 초기화 시 기존 대화 히스토리와 시스템 메시지 초기화
    st.session_state.chat_history = [
        SystemMessage(content="모든 응답은 한국어로 해 주세요.")
    ]
    st.session_state.llm_history = []  # LLM에게 전달할 대화 내용도 초기화
    st.rerun()  # 페이지 새로 고침

# ⏳ 에이전트 호출 함수
async def ask_agent(full_messages):
    model = ChatOpenAI(model="gpt-4o", openai_api_key=openai_api_key)

    # SystemMessage + 최근 3개 대화만
    system_msg = full_messages[0:1]
    dialogue = full_messages[1:]
    recent_dialogue = dialogue[-3:]
    trimmed_messages = system_msg + recent_dialogue

    # 디버깅: 최종 메시지
    # with st.expander("📄 최종 메시지 (디버깅)", expanded=False):
    #     st.write(trimmed_messages)

    async with MultiServerMCPClient(
        {
            "pg-mcp-server": {
                "url": "http://mcp-server:8000/sse",
                "transport": "sse",
            }
        }
    ) as client:
        agent = create_react_agent(model, client.get_tools())
        start = time.time()
        res = await agent.ainvoke({"messages": trimmed_messages})
        print("에이전트 응답 시간:", time.time() - start)

        # 전체 응답 구조 보기
        # with st.expander("🧪 에이전트 응답 구조 (디버깅)", expanded=False):
        #     st.json(res)

        # 실제 응답 메시지 추출
        if 'messages' in res:
            for message in reversed(res['messages']):
                if isinstance(message, AIMessage):
                    return message

        return AIMessage(content="응답에 문제가 발생했습니다.")

# 💬 채팅 UI: 이전 대화 불러오기
for msg in st.session_state.chat_history:
    if isinstance(msg, HumanMessage):
        with st.chat_message("user"):
            st.markdown(msg.content)
    elif isinstance(msg, AIMessage):
        with st.chat_message("ai"):
            st.markdown(msg.content)

# 📥 사용자 입력 받기
user_input = st.chat_input("메시지를 입력하세요.")
if user_input:
    # 사용자 메시지 추가
    st.session_state.chat_history.append(HumanMessage(content=user_input))

    # 사용자 메시지 출력
    with st.chat_message("user"):
        st.markdown(user_input)

    # 비동기 AI 응답 처리 함수
    async def process_ai_response():
        # AI 응답 생성 대기
        ai_msg = await ask_agent(st.session_state.chat_history)

        # 응답 메시지 세션에 저장
        st.session_state.chat_history.append(ai_msg)

        # AI 응답을 출력
        return ai_msg.content  # 여기에 응답 내용을 반환

    # 비동기 함수 실행
    loop = asyncio.get_event_loop()
    ai_msg_content = loop.run_until_complete(process_ai_response())  # 대기 후 결과 받기

    # AI 메시지 출력
    with st.chat_message("ai"):
        st.markdown(ai_msg_content)  # 비동기 작업이 끝난 후에 출력
