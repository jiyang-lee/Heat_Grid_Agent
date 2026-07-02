"""langgraph StateGraph — START→llm, llm-(tool_calls)→tools→llm, llm-(없음)→END.

참조 패턴(6_langgraph_tools): State.messages(add_messages) + llm_node + ToolNode + route_tools.
ChatOpenAI 사용. (오프라인 한 사이클은 run_agent._run_offline 가 동일 tool 을 직접 호출.)
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from agent.llm import tools as tools_mod


class State(TypedDict):
    messages: Annotated[list, add_messages]


def route_tools(state: State):
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return END


def build_graph(model_name: str = "gpt-4o-mini", temperature: float = 0.0):
    """ChatOpenAI 기반 그래프를 컴파일해 반환한다. (OPENAI_API_KEY 필요)"""
    from langchain_openai import ChatOpenAI  # import 지연: 키 없을 때도 모듈 로드 가능

    llm = ChatOpenAI(model=model_name, temperature=temperature).bind_tools(
        tools_mod.ALL_TOOLS
    )

    def llm_node(state: State):
        return {"messages": [llm.invoke(state["messages"])]}

    graph = StateGraph(State)
    graph.add_node("llm", llm_node)
    graph.add_node("tools", ToolNode(tools_mod.ALL_TOOLS))
    graph.add_edge(START, "llm")
    graph.add_conditional_edges("llm", route_tools, {"tools": "tools", END: END})
    graph.add_edge("tools", "llm")
    return graph.compile()
