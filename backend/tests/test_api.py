"""Tests for FastAPI endpoints (/api/query, /api/courses, /api/session/clear).

This module defines a test app that mirrors the production API endpoints
but excludes static file mounting which requires the frontend directory.
"""

from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from typing import List, Optional


# ---------------------------------------------------------------------------
# Test App (mirrors production API without static files)
# ---------------------------------------------------------------------------

def create_test_app(mock_rag_system: MagicMock) -> FastAPI:
    """Create a test FastAPI app with mocked RAGSystem."""
    app = FastAPI(title="Test Course Materials RAG System")

    class QueryRequest(BaseModel):
        query: str
        session_id: Optional[str] = None

    class QueryResponse(BaseModel):
        answer: str
        sources: List[dict]
        session_id: str

    class CourseStats(BaseModel):
        total_courses: int
        course_titles: List[str]

    class ClearSessionRequest(BaseModel):
        session_id: str

    @app.post("/api/query", response_model=QueryResponse)
    async def query_documents(request: QueryRequest):
        try:
            session_id = request.session_id
            if not session_id:
                session_id = mock_rag_system.session_manager.create_session()
            answer, sources = mock_rag_system.query(request.query, session_id)
            return QueryResponse(
                answer=answer,
                sources=sources,
                session_id=session_id,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/courses", response_model=CourseStats)
    async def get_course_stats():
        try:
            analytics = mock_rag_system.get_course_analytics()
            return CourseStats(
                total_courses=analytics["total_courses"],
                course_titles=analytics["course_titles"],
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/session/clear")
    async def clear_session(request: ClearSessionRequest):
        mock_rag_system.session_manager.clear_session(request.session_id)
        return {"status": "cleared"}

    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_client(mock_rag_system):
    """Create a test client with mocked RAGSystem."""
    app = create_test_app(mock_rag_system)
    return TestClient(app), mock_rag_system


# ---------------------------------------------------------------------------
# /api/query endpoint tests
# ---------------------------------------------------------------------------

class TestQueryEndpoint:
    def test_query_with_session_id(self, test_client):
        """POST /api/query with existing session_id uses that session."""
        client, mock_rag = test_client

        response = client.post(
            "/api/query",
            json={"query": "What is Python?", "session_id": "existing-session"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "existing-session"
        assert data["answer"] == "Test answer"
        assert len(data["sources"]) > 0
        mock_rag.query.assert_called_once_with("What is Python?", "existing-session")

    def test_query_without_session_id_creates_new(self, test_client):
        """POST /api/query without session_id creates a new session."""
        client, mock_rag = test_client

        response = client.post("/api/query", json={"query": "What is Python?"})

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-session-id"
        mock_rag.session_manager.create_session.assert_called_once()

    def test_query_returns_sources(self, test_client):
        """POST /api/query returns sources in response."""
        client, mock_rag = test_client

        response = client.post("/api/query", json={"query": "Neural networks"})

        assert response.status_code == 200
        data = response.json()
        assert "sources" in data
        assert isinstance(data["sources"], list)
        assert data["sources"][0]["text"] == "Source text"

    def test_query_missing_query_field(self, test_client):
        """POST /api/query without query field returns 422."""
        client, _ = test_client

        response = client.post("/api/query", json={})

        assert response.status_code == 422

    def test_query_empty_query_string(self, test_client):
        """POST /api/query with empty query string is still processed."""
        client, mock_rag = test_client

        response = client.post("/api/query", json={"query": ""})

        assert response.status_code == 200
        mock_rag.query.assert_called_once()

    def test_query_internal_error(self, test_client):
        """POST /api/query returns 500 when RAGSystem raises exception."""
        client, mock_rag = test_client
        mock_rag.query.side_effect = Exception("Internal error")

        response = client.post("/api/query", json={"query": "test"})

        assert response.status_code == 500
        assert "Internal error" in response.json()["detail"]


# ---------------------------------------------------------------------------
# /api/courses endpoint tests
# ---------------------------------------------------------------------------

class TestCoursesEndpoint:
    def test_get_courses(self, test_client):
        """GET /api/courses returns course statistics."""
        client, _ = test_client

        response = client.get("/api/courses")

        assert response.status_code == 200
        data = response.json()
        assert data["total_courses"] == 2
        assert "Introduction to Python" in data["course_titles"]
        assert "Advanced Machine Learning" in data["course_titles"]

    def test_get_courses_internal_error(self, test_client):
        """GET /api/courses returns 500 when get_course_analytics raises."""
        client, mock_rag = test_client
        mock_rag.get_course_analytics.side_effect = Exception("DB error")

        response = client.get("/api/courses")

        assert response.status_code == 500
        assert "DB error" in response.json()["detail"]


# ---------------------------------------------------------------------------
# /api/session/clear endpoint tests
# ---------------------------------------------------------------------------

class TestSessionClearEndpoint:
    def test_clear_session(self, test_client):
        """POST /api/session/clear clears the specified session."""
        client, mock_rag = test_client

        response = client.post(
            "/api/session/clear",
            json={"session_id": "session-to-clear"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "cleared"
        mock_rag.session_manager.clear_session.assert_called_once_with("session-to-clear")

    def test_clear_session_missing_id(self, test_client):
        """POST /api/session/clear without session_id returns 422."""
        client, _ = test_client

        response = client.post("/api/session/clear", json={})

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Request/Response format tests
# ---------------------------------------------------------------------------

class TestRequestResponseFormats:
    def test_query_response_format(self, test_client):
        """QueryResponse has correct field types."""
        client, _ = test_client

        response = client.post("/api/query", json={"query": "test"})
        data = response.json()

        assert isinstance(data["answer"], str)
        assert isinstance(data["sources"], list)
        assert isinstance(data["session_id"], str)

    def test_course_stats_response_format(self, test_client):
        """CourseStats has correct field types."""
        client, _ = test_client

        response = client.get("/api/courses")
        data = response.json()

        assert isinstance(data["total_courses"], int)
        assert isinstance(data["course_titles"], list)
        assert all(isinstance(title, str) for title in data["course_titles"])


# ---------------------------------------------------------------------------
# CORS and headers tests
# ---------------------------------------------------------------------------

class TestCORSAndHeaders:
    def test_json_content_type(self, test_client):
        """API responses have application/json content type."""
        client, _ = test_client

        response = client.get("/api/courses")

        assert "application/json" in response.headers["content-type"]

    def test_post_accepts_json(self, test_client):
        """POST endpoints accept application/json."""
        client, _ = test_client

        response = client.post(
            "/api/query",
            json={"query": "test"},
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200
