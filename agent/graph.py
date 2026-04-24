"""LangGraph agent: Gemini + MCP tools + custom tools."""

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver

from agent.tools import analyze_food_photo, calculate_bmi, calculate_kbzhu, generate_workout_plan, search_knowledge

logging.getLogger("google.genai").setLevel(logging.ERROR)

PROJECT_ROOT = str(Path(__file__).parent.parent)
PYTHON = sys.executable

CUSTOM_TOOLS = [analyze_food_photo, calculate_bmi, calculate_kbzhu, generate_workout_plan, search_knowledge]

_graph = None
_client = None
_memory = MemorySaver()


def _build_mcp_config() -> dict:
    # The MCP library's stdio_client uses get_default_environment() which only
    # passes HOME and PATH to subprocesses. We must explicitly forward the
    # variables that the MCP servers need (database connection, Gemini API key).
    mcp_env = {
        k: v
        for k in ("DATABASE_URL", "GEMINI_API_KEY", "GEMINI_MODEL", "JWT_SECRET")
        if (v := os.getenv(k))
    }
    return {
        "fitness": {
            "command": PYTHON,
            "args": [os.path.join(PROJECT_ROOT, "mcp_servers", "fitness_mcp.py")],
            "transport": "stdio",
            "env": mcp_env,
        },
        "nutrition": {
            "command": PYTHON,
            "args": [os.path.join(PROJECT_ROOT, "mcp_servers", "nutrition_mcp.py")],
            "transport": "stdio",
            "env": mcp_env,
        },
    }


async def get_graph():
    """Get or create the singleton agent graph with memory."""
    global _graph, _client
    if _graph is not None:
        return _graph

    _client = MultiServerMCPClient(_build_mcp_config())
    try:
        mcp_tools = await _client.get_tools()
    except Exception:
        logger.exception("Failed to load MCP tools; falling back to custom tools only")
        mcp_tools = []
    all_tools = mcp_tools + CUSTOM_TOOLS

    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0.7,
    )

    model_with_tools = llm.bind_tools(all_tools)

    async def call_model(state: MessagesState):
        response = await model_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", call_model)
    builder.add_node("tools", ToolNode(all_tools, handle_tool_errors=True))
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    _graph = builder.compile(checkpointer=_memory)

    return _graph


async def cleanup():
    global _graph, _client
    _graph = None
    if _client:
        try:
            await _client.__aexit__(None, None, None)
        except Exception:
            logger.warning("Error during MCP client cleanup", exc_info=True)
        _client = None
