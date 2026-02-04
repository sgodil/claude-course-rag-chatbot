"""Tests for CourseSearchTool, ToolManager, and VectorStore search behavior."""

from config import Config
from search_tools import CourseSearchTool, ToolManager

# ---------------------------------------------------------------------------
# Config-level: confirm the bug exists in the default Config
# ---------------------------------------------------------------------------


class TestConfigBug:
    def test_config_max_results_is_five(self):
        """The default Config now has MAX_RESULTS=5 (bug fixed)."""
        cfg = Config()
        assert cfg.MAX_RESULTS == 5


# ---------------------------------------------------------------------------
# VectorStore.search() with zero vs. non-zero max_results
# ---------------------------------------------------------------------------


class TestVectorStoreSearch:
    def test_vector_store_search_with_zero_max_results(self, buggy_vector_store):
        """ChromaDB rejects n_results=0, so search returns an error."""
        results = buggy_vector_store.search("Python variables")
        assert results.error is not None
        assert "Search error" in results.error
        assert results.is_empty()

    def test_vector_store_search_with_explicit_limit(self, buggy_vector_store):
        """Even with max_results=0, an explicit limit overrides and succeeds."""
        results = buggy_vector_store.search("Python variables", limit=3)
        assert results.error is None
        assert not results.is_empty()
        assert len(results.documents) > 0

    def test_vector_store_search_with_fixed_max_results(self, fixed_vector_store):
        """With max_results=5 the default search works normally."""
        results = fixed_vector_store.search("neural networks")
        assert results.error is None
        assert not results.is_empty()
        assert len(results.documents) > 0


# ---------------------------------------------------------------------------
# CourseSearchTool.execute()
# ---------------------------------------------------------------------------


class TestCourseSearchToolExecute:
    def test_course_search_tool_execute_returns_error(self, buggy_vector_store):
        """With max_results=0, execute() returns the ChromaDB error string."""
        tool = CourseSearchTool(buggy_vector_store)
        result = tool.execute(query="Python variables")
        assert "Search error" in result or "error" in result.lower()

    def test_course_search_tool_execute_with_fixed_store(self, fixed_vector_store):
        """With max_results=5, execute() returns actual content."""
        tool = CourseSearchTool(fixed_vector_store)
        result = tool.execute(query="Python variables")
        # Should contain actual course content, not an error
        assert "Search error" not in result
        assert "Python" in result or "variable" in result.lower()

    def test_course_search_tool_with_course_filter(self, fixed_vector_store):
        """Filtering by course name returns only results from that course."""
        tool = CourseSearchTool(fixed_vector_store)
        result = tool.execute(query="lessons", course_name="Introduction to Python")
        assert "Search error" not in result
        # Result should reference the Python course, not ML
        assert "Introduction to Python" in result

    def test_course_search_tool_with_lesson_filter(self, fixed_vector_store):
        """Filtering by lesson number narrows results to that lesson."""
        tool = CourseSearchTool(fixed_vector_store)
        result = tool.execute(
            query="neural networks",
            course_name="Advanced Machine Learning",
            lesson_number=1,
        )
        assert "Search error" not in result
        # Should include content from ML lesson 1
        assert "neural" in result.lower() or "Advanced Machine Learning" in result

    def test_course_search_tool_nonexistent_course(self, fixed_vector_store):
        """Searching for a nonexistent course still returns results due to fuzzy matching.

        VectorStore._resolve_course_name uses semantic search, so even a
        nonsense name will match the closest existing course rather than
        returning 'not found'.  This test verifies the tool does not crash
        and returns a string result (possibly from the nearest match).
        """
        tool = CourseSearchTool(fixed_vector_store)
        result = tool.execute(
            query="anything", course_name="Nonexistent Course XYZ 999"
        )
        # The fuzzy resolver will pick the closest course; we just verify
        # the tool completes without error and returns a non-empty string.
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# ToolManager wiring
# ---------------------------------------------------------------------------


class TestToolManager:
    def test_tool_manager_dispatch(self, buggy_vector_store):
        """ToolManager.execute_tool dispatches to the correct registered tool."""
        tm = ToolManager()
        search_tool = CourseSearchTool(buggy_vector_store)
        tm.register_tool(search_tool)

        result = tm.execute_tool("search_course_content", query="Python variables")
        # With the buggy store this should be the error string
        assert isinstance(result, str)
        assert "Search error" in result or "error" in result.lower()

    def test_tool_definition_format(self, buggy_vector_store):
        """Tool definitions conform to the Anthropic tool-use schema."""
        tool = CourseSearchTool(buggy_vector_store)
        defn = tool.get_tool_definition()

        assert defn["name"] == "search_course_content"
        assert "input_schema" in defn
        schema = defn["input_schema"]
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "required" in schema
        assert "query" in schema["required"]
