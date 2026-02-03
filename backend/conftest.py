import sys
import os
import tempfile
import shutil
from dataclasses import dataclass

import pytest

# Allow bare imports from the backend directory (e.g. `from vector_store import ...`)
sys.path.insert(0, os.path.dirname(__file__))

from vector_store import VectorStore
from models import Course, Lesson, CourseChunk


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

TEST_COURSES = [
    Course(
        title="Introduction to Python",
        course_link="https://example.com/python",
        instructor="Alice",
        lessons=[
            Lesson(lesson_number=1, title="Variables and Types", lesson_link="https://example.com/python/1"),
            Lesson(lesson_number=2, title="Control Flow", lesson_link="https://example.com/python/2"),
        ],
    ),
    Course(
        title="Advanced Machine Learning",
        course_link="https://example.com/ml",
        instructor="Bob",
        lessons=[
            Lesson(lesson_number=1, title="Neural Networks", lesson_link="https://example.com/ml/1"),
            Lesson(lesson_number=2, title="Transformers", lesson_link="https://example.com/ml/2"),
        ],
    ),
]

TEST_CHUNKS = [
    # Python course chunks
    CourseChunk(content="Python variables can hold integers, strings, and floats. Use assignment with the equals sign.", course_title="Introduction to Python", lesson_number=1, chunk_index=0),
    CourseChunk(content="Control flow in Python uses if, elif, and else statements. For loops iterate over sequences.", course_title="Introduction to Python", lesson_number=2, chunk_index=1),
    # ML course chunks
    CourseChunk(content="Neural networks consist of layers of interconnected nodes. Each node applies an activation function.", course_title="Advanced Machine Learning", lesson_number=1, chunk_index=0),
    CourseChunk(content="Transformers use self-attention mechanisms to process sequences in parallel rather than sequentially.", course_title="Advanced Machine Learning", lesson_number=2, chunk_index=1),
]


def _add_test_data(store: VectorStore):
    """Populate a VectorStore with the canonical test courses and chunks."""
    for course in TEST_COURSES:
        store.add_course_metadata(course)
    store.add_course_content(TEST_CHUNKS)


# ---------------------------------------------------------------------------
# Config dataclasses (mirrors backend/config.py shape)
# ---------------------------------------------------------------------------

@dataclass
class BuggyConfig:
    """Config with MAX_RESULTS=0, reproducing the bug."""
    ANTHROPIC_API_KEY: str = "test-key-not-real"
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 100
    MAX_RESULTS: int = 0
    MAX_HISTORY: int = 2
    CHROMA_PATH: str = ""  # set per-fixture


@dataclass
class FixedConfig:
    """Config with MAX_RESULTS=5, representing the fix."""
    ANTHROPIC_API_KEY: str = "test-key-not-real"
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 100
    MAX_RESULTS: int = 5
    MAX_HISTORY: int = 2
    CHROMA_PATH: str = ""  # set per-fixture


# ---------------------------------------------------------------------------
# Session-scoped VectorStore fixtures (expensive — built once per test run)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def buggy_vector_store(tmp_path_factory):
    """VectorStore with max_results=0, reproducing the ChromaDB n_results bug."""
    db_dir = str(tmp_path_factory.mktemp("chroma_buggy"))
    store = VectorStore(chroma_path=db_dir, embedding_model="all-MiniLM-L6-v2", max_results=0)
    _add_test_data(store)
    return store


@pytest.fixture(scope="session")
def fixed_vector_store(tmp_path_factory):
    """VectorStore with max_results=5, representing the fix."""
    db_dir = str(tmp_path_factory.mktemp("chroma_fixed"))
    store = VectorStore(chroma_path=db_dir, embedding_model="all-MiniLM-L6-v2", max_results=5)
    _add_test_data(store)
    return store


# ---------------------------------------------------------------------------
# Config fixtures (function-scoped so tests can mutate freely)
# ---------------------------------------------------------------------------

@pytest.fixture
def test_config(tmp_path):
    """Buggy config (MAX_RESULTS=0) with a unique ChromaDB temp path."""
    cfg = BuggyConfig()
    cfg.CHROMA_PATH = str(tmp_path / "chroma_buggy")
    return cfg


@pytest.fixture
def fixed_config(tmp_path):
    """Fixed config (MAX_RESULTS=5) with a unique ChromaDB temp path."""
    cfg = FixedConfig()
    cfg.CHROMA_PATH = str(tmp_path / "chroma_fixed")
    return cfg
