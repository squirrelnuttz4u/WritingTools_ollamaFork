"""Unit tests for the Ollama proxy. Mocks out requests so no real Ollama is needed."""
import importlib
import os
import sys
from unittest.mock import patch, MagicMock

import pytest
import requests


@pytest.fixture
def make_app():
    """Reload app module so env-var-driven config picks up per-test values."""
    def _factory(env: dict):
        for k in ("API_KEY", "OLLAMA_URL", "OLLAMA_MODEL", "CORS_ORIGINS"):
            os.environ.pop(k, None)
        os.environ.update(env)
        sys.modules.pop("app", None)
        mod = importlib.import_module("app")
        mod.app.config["TESTING"] = True
        return mod
    return _factory


def _mock_chat_response(text="hello world", model="llama3.1:8b"):
    r = MagicMock()
    r.raise_for_status.return_value = None
    r.json.return_value = {"message": {"content": text}, "model": model, "done": True}
    return r


# -------------------- /health --------------------

def test_health_ok(make_app):
    mod = make_app({})
    with patch.object(mod.requests, "get") as m_get:
        ok = MagicMock()
        ok.raise_for_status.return_value = None
        m_get.return_value = ok
        resp = mod.app.test_client().get("/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["ollama_reachable"] is True


def test_health_down(make_app):
    mod = make_app({})
    with patch.object(mod.requests, "get", side_effect=requests.ConnectionError("nope")):
        resp = mod.app.test_client().get("/health")
    assert resp.status_code == 503
    body = resp.get_json()
    assert body["ollama_reachable"] is False


# -------------------- /rewrite --------------------

def test_rewrite_requires_text(make_app):
    mod = make_app({})
    resp = mod.app.test_client().post("/rewrite", json={"tone": "professional"})
    assert resp.status_code == 400


def test_rewrite_returns_shape(make_app):
    mod = make_app({})
    with patch.object(mod.requests, "post", return_value=_mock_chat_response("Rewritten.")):
        resp = mod.app.test_client().post(
            "/rewrite",
            json={"text": "hi team, here is the status.", "tone": "professional"},
        )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["text"] == "Rewritten."
    assert body["tone"] == "professional"
    assert body["model"] == "llama3.1:8b"


def test_rewrite_unknown_tone(make_app):
    mod = make_app({})
    resp = mod.app.test_client().post(
        "/rewrite",
        json={"text": "hi", "tone": "pirate"},
    )
    assert resp.status_code == 400


def test_rewrite_professional_tone_in_prompt(make_app):
    """Verify the tone instruction and system prompt are sent to Ollama."""
    mod = make_app({})
    with patch.object(mod.requests, "post", return_value=_mock_chat_response()) as m_post:
        mod.app.test_client().post(
            "/rewrite",
            json={"text": "draft content here", "tone": "professional"},
        )
    assert m_post.call_count == 1
    payload = m_post.call_args.kwargs["json"]
    assert payload["model"] == "llama3.1:8b"
    messages = payload["messages"]
    assert messages[0]["role"] == "system"
    assert "rewrites email drafts" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "polished, professional business tone" in messages[1]["content"]
    assert "draft content here" in messages[1]["content"]


# -------------------- auth --------------------

def test_rewrite_requires_bearer_when_api_key_set(make_app):
    mod = make_app({"API_KEY": "s3cr3t"})
    client = mod.app.test_client()

    # Missing header -> 401
    resp = client.post("/rewrite", json={"text": "hi", "tone": "professional"})
    assert resp.status_code == 401

    # Wrong key -> 401
    resp = client.post(
        "/rewrite",
        json={"text": "hi", "tone": "professional"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 401

    # Correct key -> 200
    with patch.object(mod.requests, "post", return_value=_mock_chat_response()):
        resp = client.post(
            "/rewrite",
            json={"text": "hi", "tone": "professional"},
            headers={"Authorization": "Bearer s3cr3t"},
        )
    assert resp.status_code == 200


def test_health_bypasses_auth(make_app):
    mod = make_app({"API_KEY": "s3cr3t"})
    with patch.object(mod.requests, "get") as m_get:
        ok = MagicMock()
        ok.raise_for_status.return_value = None
        m_get.return_value = ok
        resp = mod.app.test_client().get("/health")
    assert resp.status_code == 200
