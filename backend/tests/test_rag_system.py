"""Integration tests for RAGSystem — real VectorStore + real ToolManager, mocked Anthropic client."""

from unittest.mock import patch, MagicMock
from types import SimpleNamespace

import pytest
from conftest import _add_test_data, BuggyConfig, FixedConfig


# ---------------------------------------------------------------------------
# Helpers (same mock builders as test_ai_generator)
# ---------------------------------------------------------------------------

def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(tool_id, name, tool_input):
    return SimpleNamespace(type="tool_use", id=tool_id, name=name, input=tool_input)


def _make_response(content_blocks, stop_reason="end_turn"):
    return SimpleNamespace(content=content_blocks, stop_reason=stop_reason)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRAGSystemInitialization:
    def test_initialization_propagates_buggy_max_results(self, test_config):
        """RAGSystem with buggy config (MAX_RESULTS=0) sets vector_store.max_results to 0."""
        with patch("ai_generator.anthropic.Anthropic"):
            from rag_system import RAGSystem
            rag = RAGSystem(test_config)
            # test_config still uses MAX_RESULTS=0 to exercise the buggy path
            assert rag.vector_store.max_results == 0


class TestRAGSystemQuery:
    @patch("ai_generator.anthropic.Anthropic")
    def test_query_hits_search_error_with_buggy_config(self, MockAnthropic, test_config):
        """Full flow: with MAX_RESULTS=0, the tool result contains a ChromaDB error."""
        mock_client = MockAnthropic.return_value

        # Claude wants to call the search tool
        tool_block = _tool_use_block(
            "toolu_1", "search_course_content", {"query": "Python variables"}
        )
        first_response = _make_response([tool_block], stop_reason="tool_use")

        # After receiving the (error) tool result, Claude apologizes
        second_response = _make_response(
            [_text_block("I'm sorry, the search encountered an error.")],
            stop_reason="end_turn",
        )
        mock_client.messages.create.side_effect = [first_response, second_response]

        from rag_system import RAGSystem
        rag = RAGSystem(test_config)
        _add_test_data(rag.vector_store)

        session_id = rag.session_manager.create_session()
        response, sources = rag.query("What are Python variables?", session_id=session_id)

        # The second API call's messages should contain the search error
        second_call = mock_client.messages.create.call_args_list[1]
        messages = second_call.kwargs.get("messages") or second_call[1].get("messages")
        tool_result_msgs = [
            m for m in messages
            if m["role"] == "user" and isinstance(m["content"], list)
        ]
        assert len(tool_result_msgs) == 1
        tool_content = tool_result_msgs[0]["content"][0]["content"]
        assert "Search error" in tool_content

    @patch("ai_generator.anthropic.Anthropic")
    def test_query_succeeds_with_fixed_config(self, MockAnthropic, fixed_config):
        """Full flow: with MAX_RESULTS=5, the tool result contains actual course content."""
        mock_client = MockAnthropic.return_value

        tool_block = _tool_use_block(
            "toolu_2", "search_course_content", {"query": "Python variables"}
        )
        first_response = _make_response([tool_block], stop_reason="tool_use")

        second_response = _make_response(
            [_text_block("Python variables hold values using assignment.")],
            stop_reason="end_turn",
        )
        mock_client.messages.create.side_effect = [first_response, second_response]

        from rag_system import RAGSystem
        rag = RAGSystem(fixed_config)
        _add_test_data(rag.vector_store)

        session_id = rag.session_manager.create_session()
        response, sources = rag.query("What are Python variables?", session_id=session_id)

        # The tool result sent back to Claude should have real content
        second_call = mock_client.messages.create.call_args_list[1]
        messages = second_call.kwargs.get("messages") or second_call[1].get("messages")
        tool_result_msgs = [
            m for m in messages
            if m["role"] == "user" and isinstance(m["content"], list)
        ]
        assert len(tool_result_msgs) == 1
        tool_content = tool_result_msgs[0]["content"][0]["content"]
        assert "Search error" not in tool_content
        assert "Python" in tool_content or "variable" in tool_content.lower()


class TestRAGSystemSources:
    @patch("ai_generator.anthropic.Anthropic")
    def test_sources_empty_after_failed_search(self, MockAnthropic, test_config):
        """When the search errors, sources list is empty."""
        mock_client = MockAnthropic.return_value

        tool_block = _tool_use_block(
            "toolu_3", "search_course_content", {"query": "anything"}
        )
        first_response = _make_response([tool_block], stop_reason="tool_use")
        second_response = _make_response(
            [_text_block("Error occurred.")], stop_reason="end_turn"
        )
        mock_client.messages.create.side_effect = [first_response, second_response]

        from rag_system import RAGSystem
        rag = RAGSystem(test_config)
        _add_test_data(rag.vector_store)

        session_id = rag.session_manager.create_session()
        _, sources = rag.query("anything", session_id=session_id)
        assert sources == []

    @patch("ai_generator.anthropic.Anthropic")
    def test_sources_populated_after_successful_search(self, MockAnthropic, fixed_config):
        """When the search succeeds, sources list has entries."""
        mock_client = MockAnthropic.return_value

        tool_block = _tool_use_block(
            "toolu_4", "search_course_content", {"query": "Python variables"}
        )
        first_response = _make_response([tool_block], stop_reason="tool_use")
        second_response = _make_response(
            [_text_block("Python variables are...")], stop_reason="end_turn"
        )
        mock_client.messages.create.side_effect = [first_response, second_response]

        from rag_system import RAGSystem
        rag = RAGSystem(fixed_config)
        _add_test_data(rag.vector_store)

        session_id = rag.session_manager.create_session()
        _, sources = rag.query("What are Python variables?", session_id=session_id)
        assert len(sources) > 0
        # Each source should have a text key
        assert all("text" in s for s in sources)


class TestRAGSystemSession:
    @patch("ai_generator.anthropic.Anthropic")
    def test_session_records_exchange(self, MockAnthropic, fixed_config):
        """SessionManager records the query/response pair after a successful query."""
        mock_client = MockAnthropic.return_value

        # Direct response, no tool use
        mock_client.messages.create.return_value = _make_response(
            [_text_block("This is the answer.")], stop_reason="end_turn"
        )

        from rag_system import RAGSystem
        rag = RAGSystem(fixed_config)

        session_id = rag.session_manager.create_session()
        rag.query("my question", session_id=session_id)

        history = rag.session_manager.get_conversation_history(session_id)
        assert history is not None
        assert "my question" in history.lower() or "Answer this question" in history
        assert "This is the answer." in history
