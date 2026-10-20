import httpx
import pytest


@pytest.fixture(autouse=True)
def no_live_ai(monkeypatch):
    """CI must never spend NVIDIA credits, even if a real key is inherited."""
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("LEGACY_INTERVIEW_ENABLED", raising=False)
    def blocked(*args, **kwargs):
        raise AssertionError("Real outbound HTTP is forbidden in backend tests")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
