"""Тесты для роутинга по под-агентам (agent/router.py, router_node/domain_planner
в agent/nodes.py, build_graph в agent/graph.py).

Активируется settings.enable_subagent_router — эти тесты проверяют новый путь
независимо от того, включён ли флаг в текущем окружении.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

import agent.nodes as nodes
import agent.router as router


class TestToolCoverage:
    """TOOLS_BY_DOMAIN должен покрывать ровно тот же набор инструментов,
    что зарегистрирован в agent.graph.TOOLS — без пропусков и лишнего."""

    def test_domain_prompts_keys_match_tools_by_domain_keys(self):
        assert set(router.DOMAIN_PROMPTS.keys()) == set(router.TOOLS_BY_DOMAIN.keys())

    def test_all_domains_present(self):
        assert set(router.TOOLS_BY_DOMAIN.keys()) == set(router.DOMAINS)

    def test_union_of_domain_tools_matches_graph_tools(self):
        import agent.graph as graph

        domain_tool_names = {
            t.name for tools in router.TOOLS_BY_DOMAIN.values() for t in tools
        }
        graph_tool_names = {t.name for t in graph.TOOLS}
        assert domain_tool_names == graph_tool_names

    def test_no_domain_is_empty(self):
        for domain, tools in router.TOOLS_BY_DOMAIN.items():
            assert tools, f"domain '{domain}' has no tools"


class TestResolveDomain:
    async def test_explicit_mode_short_circuits_without_llm_call(self):
        with patch("agent.chat_modes.get_mode", return_value=MagicMock(key="workout")):
            with patch("agent.router.classify_domain", new=AsyncMock()) as mock_classify:
                domain = await router.resolve_domain(telegram_user_id=1, user_message="ignored")
                assert domain == "workout"
                mock_classify.assert_not_called()

    async def test_general_mode_delegates_to_classifier(self):
        with patch("agent.chat_modes.get_mode", return_value=MagicMock(key="general")):
            with patch("agent.router.classify_domain", new=AsyncMock(return_value="progress")) as mock_classify:
                domain = await router.resolve_domain(telegram_user_id=1, user_message="вешу 82кг")
                assert domain == "progress"
                mock_classify.assert_awaited_once_with("вешу 82кг")


class TestClassifyDomain:
    async def test_parses_recognized_domain_from_response(self):
        fake_llm = MagicMock()
        fake_llm.ainvoke = AsyncMock(return_value=AIMessage(content="nutrition"))
        with patch("llm.provider.get_llm", return_value=fake_llm):
            domain = await router.classify_domain("съел овсянку")
            assert domain == "nutrition"

    async def test_falls_back_to_general_on_llm_exception(self):
        fake_llm = MagicMock()
        fake_llm.ainvoke = AsyncMock(side_effect=RuntimeError("503 unavailable"))
        with patch("llm.provider.get_llm", return_value=fake_llm):
            domain = await router.classify_domain("что угодно")
            assert domain == "general"

    async def test_falls_back_to_general_on_unrecognized_output(self):
        fake_llm = MagicMock()
        fake_llm.ainvoke = AsyncMock(return_value=AIMessage(content="не знаю, что-то странное"))
        with patch("llm.provider.get_llm", return_value=fake_llm):
            domain = await router.classify_domain("что угодно")
            assert domain == "general"


class TestRouterNode:
    async def test_returns_active_domain_from_last_message(self):
        state = {
            "telegram_user_id": 42,
            "messages": [HumanMessage(content="мотивируй меня")],
        }
        with patch("agent.router.resolve_domain", new=AsyncMock(return_value="motivation")) as mock_resolve:
            result = await nodes.router_node(state)
            assert result == {"active_domain": "motivation"}
            mock_resolve.assert_awaited_once_with(42, "мотивируй меня")

    async def test_handles_empty_messages(self):
        state = {"telegram_user_id": 42, "messages": []}
        with patch("agent.router.resolve_domain", new=AsyncMock(return_value="general")) as mock_resolve:
            result = await nodes.router_node(state)
            assert result == {"active_domain": "general"}
            mock_resolve.assert_awaited_once_with(42, "")


class TestDomainPlanner:
    async def test_binds_only_the_active_domains_tools(self):
        fake_llm = MagicMock()
        fake_llm.bind_tools.return_value = fake_llm
        fake_llm.ainvoke = AsyncMock(return_value=AIMessage(content="ok"))

        state = {
            "telegram_user_id": 42,
            "user_profile": {"injuries": []},
            "active_domain": "progress",
            "messages": [HumanMessage(content="покажи прогресс")],
        }
        with patch("agent.nodes.get_llm", return_value=fake_llm):
            await nodes.domain_planner(state)

        bound_tools = fake_llm.bind_tools.call_args[0][0]
        bound_names = {t.name for t in bound_tools}
        expected_names = {t.name for t in router.TOOLS_BY_DOMAIN["progress"]}
        assert bound_names == expected_names

    async def test_corrects_hallucinated_telegram_user_id(self):
        fake_response = AIMessage(
            content="",
            tool_calls=[
                {"name": "log_progress", "args": {"telegram_user_id": 999, "weight_kg": 80}, "id": "call_1"}
            ],
        )
        fake_llm = MagicMock()
        fake_llm.bind_tools.return_value = fake_llm
        fake_llm.ainvoke = AsyncMock(return_value=fake_response)

        state = {
            "telegram_user_id": 42,
            "user_profile": {"injuries": []},
            "active_domain": "progress",
            "messages": [HumanMessage(content="вешу 80")],
        }
        with patch("agent.nodes.get_llm", return_value=fake_llm):
            out = await nodes.domain_planner(state)

        corrected = out["messages"][0].tool_calls[0]["args"]["telegram_user_id"]
        assert corrected == 42


class TestInvokeLlmWithRetry:
    async def test_retries_on_503_then_succeeds(self):
        llm = MagicMock()
        llm.ainvoke = AsyncMock(
            side_effect=[RuntimeError("503 Service Unavailable"), AIMessage(content="ok")]
        )
        with patch("agent.nodes.asyncio.sleep", new=AsyncMock()):
            response = await nodes._invoke_llm_with_retry(llm, [], telegram_user_id=1, log_prefix="test")
        assert response.content == "ok"
        assert llm.ainvoke.await_count == 2

    async def test_raises_immediately_on_non_retryable_error(self):
        llm = MagicMock()
        llm.ainvoke = AsyncMock(side_effect=ValueError("bad request"))
        with pytest.raises(ValueError):
            await nodes._invoke_llm_with_retry(llm, [], telegram_user_id=1, log_prefix="test")
        assert llm.ainvoke.await_count == 1


class TestBuildGraph:
    def test_flag_off_builds_flat_graph(self):
        with patch("agent.graph.settings") as mock_settings:
            mock_settings.enable_subagent_router = False
            from agent.graph import build_graph

            g = build_graph()
            nodes_ = set(g.get_graph().nodes.keys())
            assert "planner" in nodes_
            assert "router" not in nodes_
            assert "domain_planner" not in nodes_

    def test_flag_on_builds_routed_graph(self):
        with patch("agent.graph.settings") as mock_settings:
            mock_settings.enable_subagent_router = True
            from agent.graph import build_graph

            g = build_graph()
            nodes_ = set(g.get_graph().nodes.keys())
            assert "router" in nodes_
            assert "domain_planner" in nodes_
            assert "planner" not in nodes_
