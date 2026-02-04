"""Shared pytest fixtures for RAG system tests."""

import sys
import tempfile
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from unittest.mock import patch, MagicMock

import pytest

# Ensure backend modules can be imported
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config
from vector_store import VectorStore
from models import Course, CourseChunk, Lesson


# ---------------------------------------------------------------------------
# Config fixtures
# ---------------------------------------------------------------------------

@dataclass
class BuggyConfig(Config):
    """Config with MAX_RESULTS=0 to exercise the buggy code path."""
    MAX_RESULTS: int = field(default=0)


@dataclass
class FixedConfig(Config):
    """Config with MAX_RESULTS=5 (the fixed configuration)."""
    MAX_RESULTS: int = field(default=5)


@pytest.fixture
def test_config():
    """Return a buggy config (MAX_RESULTS=0) for testing error paths."""
    return BuggyConfig()


@pytest.fixture
def fixed_config():
    """Return a fixed config (MAX_RESULTS=5) for testing success paths."""
    return FixedConfig()


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

TEST_COURSES = [
    Course(
        title="Introduction to Python",
        course_link="https://example.com/python",
        instructor="Test Instructor",
        lessons=[
            Lesson(lesson_number=1, title="Variables and Data Types", lesson_link="https://example.com/python#1"),
            Lesson(lesson_number=2, title="Functions", lesson_link="https://example.com/python#2"),
        ],
    ),
    Course(
        title="Advanced Machine Learning",
        course_link="https://example.com/ml",
        instructor="Test Instructor",
        lessons=[
            Lesson(lesson_number=1, title="Neural Network Fundamentals", lesson_link="https://example.com/ml#1"),
            Lesson(lesson_number=2, title="Deep Learning", lesson_link="https://example.com/ml#2"),
        ],
    ),
]

TEST_CHUNKS = [
    CourseChunk(
        content="Python variables are containers for storing data values. "
                "You can create a variable by simply assigning a value to it.",
        course_title="Introduction to Python",
        lesson_number=1,
        chunk_index=0,
    ),
    CourseChunk(
        content="Functions in Python are defined using the def keyword. "
                "Functions help organize code and make it reusable.",
        course_title="Introduction to Python",
        lesson_number=2,
        chunk_index=1,
    ),
    CourseChunk(
        content="Neural networks are computational models inspired by the human brain. "
                "They consist of layers of interconnected nodes called neurons.",
        course_title="Advanced Machine Learning",
        lesson_number=1,
        chunk_index=2,
    ),
    CourseChunk(
        content="Deep learning uses multi-layer neural networks to learn complex patterns. "
                "Backpropagation is the key algorithm for training these networks.",
        course_title="Advanced Machine Learning",
        lesson_number=2,
        chunk_index=3,
    ),
]


def _add_test_data(vector_store: VectorStore) -> None:
    """Populate a VectorStore with test documents."""
    # Add course metadata
    for course in TEST_COURSES:
        vector_store.add_course_metadata(course)

    # Add course content chunks
    vector_store.add_course_content(TEST_CHUNKS)


# ---------------------------------------------------------------------------
# VectorStore fixtures with temporary ChromaDB
# ---------------------------------------------------------------------------

@pytest.fixture
def buggy_vector_store(test_config):
    """VectorStore with MAX_RESULTS=0 using a temporary ChromaDB."""
    temp_dir = tempfile.mkdtemp()
    try:
        vs = VectorStore(
            chroma_path=temp_dir,
            embedding_model=test_config.EMBEDDING_MODEL,
            max_results=test_config.MAX_RESULTS,
        )
        _add_test_data(vs)
        yield vs
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def fixed_vector_store(fixed_config):
    """VectorStore with MAX_RESULTS=5 using a temporary ChromaDB."""
    temp_dir = tempfile.mkdtemp()
    try:
        vs = VectorStore(
            chroma_path=temp_dir,
            embedding_model=fixed_config.EMBEDDING_MODEL,
            max_results=fixed_config.MAX_RESULTS,
        )
        _add_test_data(vs)
        yield vs
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Mock Anthropic client fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_anthropic():
    """Patch the Anthropic client for testing without API calls."""
    with patch("ai_generator.anthropic.Anthropic") as mock:
        yield mock


# ---------------------------------------------------------------------------
# API test fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_rag_system():
    """Create a mock RAGSystem for API testing."""
    mock = MagicMock()
    mock.session_manager.create_session.return_value = "test-session-id"
    mock.query.return_value = ("Test answer", [{"text": "Source text", "course": "Test Course"}])
    mock.get_course_analytics.return_value = {
        "total_courses": 2,
        "course_titles": ["Introduction to Python", "Advanced Machine Learning"],
    }
    return mock
