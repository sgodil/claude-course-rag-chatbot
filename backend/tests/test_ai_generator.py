"""Tests for AIGenerator with mocked Anthropic client (no real API calls)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ai_generator import AIGenerator
from search_tools import ToolManager

# ---------------------------------------------------------------------------
# Helpers to build mock Anthropic response objects
# ---------------------------------------------------------------------------


def _text_block(text):
    """Simulate an anthropic TextBlock."""
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(tool_id, name, tool_input):
    """Simulate an anthropic ToolUseBlock."""
    return SimpleNamespace(type="tool_use", id=tool_id, name=name, input=tool_input)


def _make_response(content_blocks, stop_reason="end_turn"):
    """Build a mock messages.create() return value."""
    return SimpleNamespace(content=content_blocks, stop_reason=stop_reason)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAIGeneratorDirectResponse:
    @patch("ai_generator.anthropic.Anthropic")
    def test_direct_response_no_tool_use(self, MockAnthropic):
        """When Claude returns text directly, generate_response returns it."""
        mock_client = MockAnthropic.return_value
        mock_client.messages.create.return_value = _make_response(
            [_text_block("Hello, I can help with that.")], stop_reason="end_turn"
        )

        gen = AIGenerator(api_key="fake", model="test-model")
        result = gen.generate_response("What is Python?")

        assert result == "Hello, I can help with that."
        mock_client.messages.create.assert_called_once()


class TestAIGeneratorToolUse:
    @patch("ai_generator.anthropic.Anthropic")
    def test_tool_use_calls_tool_manager(self, MockAnthropic):
        """When stop_reason is tool_use, AIGenerator calls tool_manager.execute_tool."""
        mock_client = MockAnthropic.return_value

        # First call: Claude wants to use a tool
        tool_block = _tool_use_block(
            "toolu_123", "search_course_content", {"query": "Python"}
        )
        first_response = _make_response([tool_block], stop_reason="tool_use")

        # Second call: Claude returns final text
        second_response = _make_response(
            [_text_block("Python is a programming language.")], stop_reason="end_turn"
        )
        mock_client.messages.create.side_effect = [first_response, second_response]

        mock_tm = MagicMock(spec=ToolManager)
        mock_tm.execute_tool.return_value = "Tool result: Python variables info"

        gen = AIGenerator(api_key="fake", model="test-model")
        tools = [
            {
                "name": "search_course_content",
                "description": "Search",
                "input_schema": {},
            }
        ]
        result = gen.generate_response(
            "Tell me about Python", tools=tools, tool_manager=mock_tm
        )

        mock_tm.execute_tool.assert_called_once_with(
            "search_course_content", query="Python"
        )
        assert result == "Python is a programming language."

        # Bug fix verification: 2nd API call should include tools and tool_choice
        second_call_kwargs = mock_client.messages.create.call_args_list[1].kwargs
        assert "tools" in second_call_kwargs
        assert second_call_kwargs["tools"] == tools
        assert "tool_choice" in second_call_kwargs
        assert second_call_kwargs["tool_choice"] == {"type": "auto"}

    @patch("ai_generator.anthropic.Anthropic")
    def test_tool_error_propagated_to_second_call(self, MockAnthropic):
        """The error string from a failed tool appears in the follow-up API messages."""
        mock_client = MockAnthropic.return_value

        tool_block = _tool_use_block(
            "toolu_err", "search_course_content", {"query": "test"}
        )
        first_response = _make_response([tool_block], stop_reason="tool_use")
        second_response = _make_response(
            [_text_block("Sorry, the search failed.")], stop_reason="end_turn"
        )
        mock_client.messages.create.side_effect = [first_response, second_response]

        mock_tm = MagicMock(spec=ToolManager)
        error_msg = (
            "Search error: Number of requested results 0, cannot be negative, or zero."
        )
        mock_tm.execute_tool.return_value = error_msg

        gen = AIGenerator(api_key="fake", model="test-model")
        tools = [
            {
                "name": "search_course_content",
                "description": "Search",
                "input_schema": {},
            }
        ]
        gen.generate_response("test query", tools=tools, tool_manager=mock_tm)

        # The second API call should contain the error in the messages
        second_call_kwargs = mock_client.messages.create.call_args_list[1]
        messages = second_call_kwargs.kwargs.get("messages") or second_call_kwargs[
            1
        ].get("messages")
        # Find the tool_result message
        tool_result_msg = [
            m
            for m in messages
            if m["role"] == "user" and isinstance(m["content"], list)
        ]
        assert len(tool_result_msg) == 1
        tool_results = tool_result_msg[0]["content"]
        assert any(tr["content"] == error_msg for tr in tool_results)

        # Bug fix verification: 2nd API call should include tools and tool_choice
        second_call_kw = mock_client.messages.create.call_args_list[1].kwargs
        assert "tools" in second_call_kw
        assert "tool_choice" in second_call_kw

    @patch("ai_generator.anthropic.Anthropic")
    def test_tool_success_propagated_to_second_call(self, MockAnthropic):
        """Successful tool content appears in the follow-up API messages."""
        mock_client = MockAnthropic.return_value

        tool_block = _tool_use_block(
            "toolu_ok", "search_course_content", {"query": "neural"}
        )
        first_response = _make_response([tool_block], stop_reason="tool_use")
        second_response = _make_response(
            [_text_block("Neural networks are...")], stop_reason="end_turn"
        )
        mock_client.messages.create.side_effect = [first_response, second_response]

        mock_tm = MagicMock(spec=ToolManager)
        success_content = (
            "[Advanced Machine Learning - Lesson 1]\nNeural networks consist of layers."
        )
        mock_tm.execute_tool.return_value = success_content

        gen = AIGenerator(api_key="fake", model="test-model")
        tools = [
            {
                "name": "search_course_content",
                "description": "Search",
                "input_schema": {},
            }
        ]
        gen.generate_response("neural networks", tools=tools, tool_manager=mock_tm)

        second_call_kwargs = mock_client.messages.create.call_args_list[1]
        messages = second_call_kwargs.kwargs.get("messages") or second_call_kwargs[
            1
        ].get("messages")
        tool_result_msg = [
            m
            for m in messages
            if m["role"] == "user" and isinstance(m["content"], list)
        ]
        assert len(tool_result_msg) == 1
        tool_results = tool_result_msg[0]["content"]
        assert any(tr["content"] == success_content for tr in tool_results)

        # Bug fix verification: 2nd API call should include tools and tool_choice
        second_call_kw = mock_client.messages.create.call_args_list[1].kwargs
        assert "tools" in second_call_kw
        assert "tool_choice" in second_call_kw


class TestAIGeneratorAPIParams:
    @patch("ai_generator.anthropic.Anthropic")
    def test_tools_included_in_api_params(self, MockAnthropic):
        """When tools are provided, tools and tool_choice are passed to the API."""
        mock_client = MockAnthropic.return_value
        mock_client.messages.create.return_value = _make_response(
            [_text_block("answer")], stop_reason="end_turn"
        )

        gen = AIGenerator(api_key="fake", model="test-model")
        tools = [
            {
                "name": "search_course_content",
                "description": "Search",
                "input_schema": {},
            }
        ]
        gen.generate_response("query", tools=tools)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "tools" in call_kwargs
        assert call_kwargs["tools"] == tools
        assert "tool_choice" in call_kwargs
        assert call_kwargs["tool_choice"] == {"type": "auto"}

    @patch("ai_generator.anthropic.Anthropic")
    def test_no_tools_omits_tool_params(self, MockAnthropic):
        """When no tools are provided, tools/tool_choice are absent from API params."""
        mock_client = MockAnthropic.return_value
        mock_client.messages.create.return_value = _make_response(
            [_text_block("answer")], stop_reason="end_turn"
        )

        gen = AIGenerator(api_key="fake", model="test-model")
        gen.generate_response("query")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "tools" not in call_kwargs
        assert "tool_choice" not in call_kwargs

    @patch("ai_generator.anthropic.Anthropic")
    def test_conversation_history_in_system_prompt(self, MockAnthropic):
        """When conversation_history is provided, it's appended to the system content."""
        mock_client = MockAnthropic.return_value
        mock_client.messages.create.return_value = _make_response(
            [_text_block("answer")], stop_reason="end_turn"
        )

        gen = AIGenerator(api_key="fake", model="test-model")
        gen.generate_response(
            "query", conversation_history="User: hi\nAssistant: hello"
        )

        call_kwargs = mock_client.messages.create.call_args.kwargs
        system_content = call_kwargs["system"]
        assert "Previous conversation:" in system_content
        assert "User: hi" in system_content
        assert "Assistant: hello" in system_content


class TestAIGeneratorMultiRoundToolUse:
    """Tests for sequential multi-round tool calling."""

    @patch("ai_generator.anthropic.Anthropic")
    def test_two_sequential_tool_calls(self, MockAnthropic):
        """Claude uses two tools sequentially: outline then search."""
        mock_client = MockAnthropic.return_value

        # Round 1: Claude calls get_course_outline
        outline_block = _tool_use_block(
            "toolu_1", "get_course_outline", {"course_name": "MCP"}
        )
        resp1 = _make_response([outline_block], stop_reason="tool_use")

        # Round 2: Claude calls search_course_content
        search_block = _tool_use_block(
            "toolu_2", "search_course_content", {"query": "MCP lesson 3"}
        )
        resp2 = _make_response([search_block], stop_reason="tool_use")

        # Round 3: Claude returns final text
        resp3 = _make_response(
            [_text_block("MCP lesson 3 covers server implementation.")],
            stop_reason="end_turn",
        )
        mock_client.messages.create.side_effect = [resp1, resp2, resp3]

        mock_tm = MagicMock(spec=ToolManager)
        mock_tm.execute_tool.side_effect = [
            "Course: MCP\nLessons:\n  1. Intro\n  2. Basics\n  3. Server Impl",
            "[MCP - Lesson 3]\nServer implementation details...",
        ]

        gen = AIGenerator(api_key="fake", model="test-model")
        tools = [
            {
                "name": "get_course_outline",
                "description": "Outline",
                "input_schema": {},
            },
            {
                "name": "search_course_content",
                "description": "Search",
                "input_schema": {},
            },
        ]
        result = gen.generate_response(
            "What does MCP lesson 3 cover?", tools=tools, tool_manager=mock_tm
        )

        # Verify 3 API calls
        assert mock_client.messages.create.call_count == 3

        # Verify 2 tool executions with correct args
        assert mock_tm.execute_tool.call_count == 2
        mock_tm.execute_tool.assert_any_call("get_course_outline", course_name="MCP")
        mock_tm.execute_tool.assert_any_call(
            "search_course_content", query="MCP lesson 3"
        )

        # Verify correct final text
        assert result == "MCP lesson 3 covers server implementation."

        # Verify 3rd call's messages list has 5 entries:
        # user query, assistant(tool1), user(result1), assistant(tool2), user(result2)
        third_call_kwargs = mock_client.messages.create.call_args_list[2].kwargs
        messages = third_call_kwargs["messages"]
        assert len(messages) == 5

    @patch("ai_generator.anthropic.Anthropic")
    def test_early_termination_no_second_tool(self, MockAnthropic):
        """Claude uses one tool then returns text — only 2 API calls."""
        mock_client = MockAnthropic.return_value

        tool_block = _tool_use_block(
            "toolu_1", "search_course_content", {"query": "Python basics"}
        )
        resp1 = _make_response([tool_block], stop_reason="tool_use")
        resp2 = _make_response(
            [_text_block("Python basics cover variables and loops.")],
            stop_reason="end_turn",
        )
        mock_client.messages.create.side_effect = [resp1, resp2]

        mock_tm = MagicMock(spec=ToolManager)
        mock_tm.execute_tool.return_value = (
            "[Python - Lesson 1]\nVariables and loops..."
        )

        gen = AIGenerator(api_key="fake", model="test-model")
        tools = [
            {
                "name": "search_course_content",
                "description": "Search",
                "input_schema": {},
            }
        ]
        result = gen.generate_response(
            "Python basics", tools=tools, tool_manager=mock_tm
        )

        assert mock_client.messages.create.call_count == 2
        assert mock_tm.execute_tool.call_count == 1
        assert result == "Python basics cover variables and loops."

    @patch("ai_generator.anthropic.Anthropic")
    def test_max_rounds_forces_text_response(self, MockAnthropic):
        """When MAX_TOOL_ROUNDS is exhausted, a forced text call is made without tools."""
        mock_client = MockAnthropic.return_value

        # Round 1: tool use
        block1 = _tool_use_block("toolu_1", "get_course_outline", {"course_name": "AI"})
        resp1 = _make_response([block1], stop_reason="tool_use")

        # Round 2: tool use again (exhausts MAX_TOOL_ROUNDS=2)
        block2 = _tool_use_block(
            "toolu_2", "search_course_content", {"query": "AI intro"}
        )
        resp2 = _make_response([block2], stop_reason="tool_use")

        # Forced text response (no tools)
        resp3 = _make_response(
            [_text_block("AI intro covers fundamentals.")], stop_reason="end_turn"
        )
        mock_client.messages.create.side_effect = [resp1, resp2, resp3]

        mock_tm = MagicMock(spec=ToolManager)
        mock_tm.execute_tool.side_effect = ["Outline data", "Search data"]

        gen = AIGenerator(api_key="fake", model="test-model")
        tools = [
            {
                "name": "get_course_outline",
                "description": "Outline",
                "input_schema": {},
            },
            {
                "name": "search_course_content",
                "description": "Search",
                "input_schema": {},
            },
        ]
        result = gen.generate_response("AI intro", tools=tools, tool_manager=mock_tm)

        # 3rd API call should NOT include tools or tool_choice (forced text)
        third_call_kwargs = mock_client.messages.create.call_args_list[2].kwargs
        assert "tools" not in third_call_kwargs
        assert "tool_choice" not in third_call_kwargs

        # Exactly 2 tool executions
        assert mock_tm.execute_tool.call_count == 2
        assert result == "AI intro covers fundamentals."

    @patch("ai_generator.anthropic.Anthropic")
    def test_tool_error_in_multi_round(self, MockAnthropic):
        """First tool returns error, second returns success — both propagated correctly."""
        mock_client = MockAnthropic.return_value

        # Round 1: tool use
        block1 = _tool_use_block(
            "toolu_1", "get_course_outline", {"course_name": "nonexistent"}
        )
        resp1 = _make_response([block1], stop_reason="tool_use")

        # Round 2: tool use
        block2 = _tool_use_block(
            "toolu_2", "search_course_content", {"query": "fallback search"}
        )
        resp2 = _make_response([block2], stop_reason="tool_use")

        # Final text
        resp3 = _make_response(
            [_text_block("No course found, but here's related content.")],
            stop_reason="end_turn",
        )
        mock_client.messages.create.side_effect = [resp1, resp2, resp3]

        mock_tm = MagicMock(spec=ToolManager)
        error_msg = "No course found matching 'nonexistent'."
        success_msg = "[General - Lesson 1]\nSome related content."
        mock_tm.execute_tool.side_effect = [error_msg, success_msg]

        gen = AIGenerator(api_key="fake", model="test-model")
        tools = [
            {
                "name": "get_course_outline",
                "description": "Outline",
                "input_schema": {},
            },
            {
                "name": "search_course_content",
                "description": "Search",
                "input_schema": {},
            },
        ]
        result = gen.generate_response(
            "nonexistent course", tools=tools, tool_manager=mock_tm
        )

        # The messages list is mutated in-place, so all call_args point to the
        # final state.  Verify via the last (forced-text) call which has the
        # complete conversation: user, asst(tool1), user(result1), asst(tool2),
        # user(result2) — 5 entries total.
        final_call_msgs = mock_client.messages.create.call_args_list[2].kwargs[
            "messages"
        ]
        assert len(final_call_msgs) == 5

        tool_result_msgs = [
            m
            for m in final_call_msgs
            if m["role"] == "user" and isinstance(m["content"], list)
        ]
        assert len(tool_result_msgs) == 2

        # First tool result contains the error
        assert any(tr["content"] == error_msg for tr in tool_result_msgs[0]["content"])
        # Second tool result contains the success
        assert any(
            tr["content"] == success_msg for tr in tool_result_msgs[1]["content"]
        )

        assert result == "No course found, but here's related content."
