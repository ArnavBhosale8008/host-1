from __future__ import annotations

import pytest

from droidpilot.ai.ollama_client import OllamaClient
from droidpilot.core.errors import AIError

from .fakes import FakeHttp, FakeResponse


def test_is_available_true():
    http = FakeHttp(get_response=FakeResponse(200, {"models": []}))
    assert OllamaClient("http://h", "m", http=http).is_available()


def test_is_available_false_on_exception():
    http = FakeHttp(get_response=ConnectionError("down"))
    assert not OllamaClient("http://h", "m", http=http).is_available()


def test_list_models():
    payload = {"models": [{"name": "llama3.1"}, {"name": "qwen2"}]}
    http = FakeHttp(get_response=FakeResponse(200, payload))
    assert OllamaClient("http://h", "m", http=http).list_models() == ["llama3.1", "qwen2"]


def test_list_models_http_error():
    http = FakeHttp(get_response=FakeResponse(500))
    with pytest.raises(AIError):
        OllamaClient("http://h", "m", http=http).list_models()


def test_chat_returns_content():
    resp = FakeResponse(200, {"message": {"content": "hello"}})
    http = FakeHttp(post_response=resp)
    client = OllamaClient("http://h", "mymodel", http=http)
    assert client.chat("sys", "user") == "hello"
    assert http.posted[0]["model"] == "mymodel"
    assert http.posted[0]["messages"][0]["role"] == "system"


def test_chat_bad_shape_raises():
    http = FakeHttp(post_response=FakeResponse(200, {"unexpected": 1}))
    with pytest.raises(AIError):
        OllamaClient("http://h", "m", http=http).chat("s", "u")


def test_chat_transport_error_raises():
    http = FakeHttp(post_response=TimeoutError("slow"))
    with pytest.raises(AIError):
        OllamaClient("http://h", "m", http=http).chat("s", "u")


def test_host_trailing_slash_stripped():
    http = FakeHttp(get_response=FakeResponse(200, {"models": []}))
    client = OllamaClient("http://h/", "m", http=http)
    assert client.is_available()
