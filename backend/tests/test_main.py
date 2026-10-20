from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import APIConnectionError, APIStatusError, APITimeoutError

import main


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    with TestClient(main.app) as client:
        yield client


@pytest.fixture
def nvidia(monkeypatch):
    mock = MagicMock()
    mock.__enter__.return_value = mock
    monkeypatch.setattr(main, "get_client", lambda: mock)
    return mock


@pytest.mark.parametrize("path", ["/", "/health", "/docs", "/openapi.json"])
def test_public_routes(client, path):
    response = client.get(path)
    assert response.status_code == 200
    if path == "/health":
        assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("payload", [
    {}, {"job_role": "x"}, {"job_role": "x" * 101},
    {"job_role": "Python Developer", "difficulty": "expert"},
])
def test_validation(client, nvidia, payload):
    assert client.post("/api/interview/start", json=payload).status_code == 422
    nvidia.chat.completions.create.assert_not_called()


def test_success(client, nvidia):
    nvidia.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=" Mock question? "))]
    )
    response = client.post("/api/interview/start", json={"job_role": "Python Developer"})
    assert response.status_code == 200
    assert response.json() == {
        "job_role": "Python Developer", "difficulty": "beginner", "question": "Mock question?"
    }
    kwargs = nvidia.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert kwargs["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False
    nvidia.__exit__.assert_called_once()


@pytest.mark.parametrize("error, status", [
    (APIConnectionError(request=httpx.Request("POST", "https://example.test")), 502),
    (APITimeoutError(request=httpx.Request("POST", "https://example.test")), 504),
    (APIStatusError("private upstream detail", response=httpx.Response(
        401, request=httpx.Request("POST", "https://example.test")
    ), body=None), 502),
])
def test_upstream_errors(client, nvidia, error, status):
    nvidia.chat.completions.create.side_effect = error
    response = client.post("/api/interview/start", json={"job_role": "Python Developer"})
    assert response.status_code == status
    assert "private upstream detail" not in response.text


@pytest.mark.parametrize("content", [None, "", "   "])
def test_empty_question(client, nvidia, content):
    nvidia.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
    assert client.post("/api/interview/start", json={"job_role": "Python Developer"}).status_code == 502


def test_missing_secret(client):
    response = client.post("/api/interview/start", json={"job_role": "Python Developer"})
    assert response.status_code == 503


def test_client_configuration(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-placeholder")
    constructor = MagicMock()
    monkeypatch.setattr(main, "OpenAI", constructor)
    main.get_client()
    constructor.assert_called_once_with(
        base_url="https://integrate.api.nvidia.com/v1", api_key="test-placeholder",
        timeout=60.0, max_retries=0,
    )


def test_cors(client):
    response = client.options("/api/interview/start", headers={
        "Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"
    })
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    response = client.get("/health", headers={"Origin": "https://untrusted.example"})
    assert "access-control-allow-origin" not in response.headers
