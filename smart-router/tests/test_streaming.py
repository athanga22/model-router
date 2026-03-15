"""Tests for /v1/chat/stream — mocked; no real LLM or DB calls."""
import json
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_frames(response_text: str) -> list[dict]:
    """Parse newline-delimited JSON from a streaming response body."""
    return [json.loads(line) for line in response_text.strip().split("\n") if line.strip()]


def _make_stream(tokens: list[str], input_tokens: int = 10, output_tokens: int = 20):
    """
    Return a generator function that mimics _stream_haiku / _stream_together /
    _stream_openai.  Accepts *args/**kwargs so it works for all three signatures.
    """
    def _gen(*args, **kwargs):
        emit = kwargs["emit"]
        full = ""
        for t in tokens:
            full += t
            yield emit(t)
        return full, input_tokens, output_tokens
    return _gen


def _post(prompt: str):
    return client.post("/v1/chat/stream", json={"prompt": prompt})


# ── Frame ordering ─────────────────────────────────────────────────────────────

class TestFrameOrdering:

    def test_metadata_frame_is_first(self):
        with patch("app.main.classify_prompt", return_value="simple"), \
             patch("app.main._stream_haiku", _make_stream(["Hello"])), \
             patch("app.main.log_request"):
            resp = _post("hi")
        assert resp.status_code == 200
        frames = _parse_frames(resp.text)
        assert frames[0]["type"] == "metadata"

    def test_done_frame_is_last(self):
        with patch("app.main.classify_prompt", return_value="simple"), \
             patch("app.main._stream_haiku", _make_stream(["Hello"])), \
             patch("app.main.log_request"):
            resp = _post("hi")
        frames = _parse_frames(resp.text)
        assert frames[-1]["type"] == "done"

    def test_token_frames_are_between_metadata_and_done(self):
        with patch("app.main.classify_prompt", return_value="simple"), \
             patch("app.main._stream_haiku", _make_stream(["Hello", " world"])), \
             patch("app.main.log_request"):
            resp = _post("hi")
        frames = _parse_frames(resp.text)
        types = [f["type"] for f in frames]
        assert types[0] == "metadata"
        assert types[-1] == "done"
        assert "token" in types

    def test_token_content_preserved(self):
        with patch("app.main.classify_prompt", return_value="simple"), \
             patch("app.main._stream_haiku", _make_stream(["Hello", " world"])), \
             patch("app.main.log_request"):
            resp = _post("hi")
        token_frames = [f for f in _parse_frames(resp.text) if f["type"] == "token"]
        assert [f["text"] for f in token_frames] == ["Hello", " world"]


# ── Metadata fields ────────────────────────────────────────────────────────────

class TestMetadataFields:

    def test_metadata_contains_required_fields(self):
        with patch("app.main.classify_prompt", return_value="simple"), \
             patch("app.main._stream_haiku", _make_stream(["ok"])), \
             patch("app.main.log_request"):
            resp = _post("hi")
        meta = _parse_frames(resp.text)[0]
        assert "model_used" in meta
        assert "difficulty_tag" in meta
        assert "escalated" in meta

    def test_metadata_model_matches_tag(self):
        with patch("app.main.classify_prompt", return_value="simple"), \
             patch("app.main._stream_haiku", _make_stream(["ok"])), \
             patch("app.main.log_request"):
            resp = _post("hi")
        meta = _parse_frames(resp.text)[0]
        assert meta["model_used"] == "claude-haiku-4-5"
        assert meta["difficulty_tag"] == "simple"

    def test_done_frame_contains_cost_info(self):
        with patch("app.main.classify_prompt", return_value="simple"), \
             patch("app.main._stream_haiku", _make_stream(["ok"], input_tokens=15, output_tokens=30)), \
             patch("app.main.log_request"):
            resp = _post("hi")
        done = _parse_frames(resp.text)[-1]
        assert done["input_tokens"] == 15
        assert done["output_tokens"] == 30
        assert done["cost_usd"] >= 0
        assert "latency_ms" in done


# ── Escalation ─────────────────────────────────────────────────────────────────

class TestStreamEscalation:

    def test_escalation_sets_metadata_escalated_true(self):
        haiku = _make_stream(["I don't know the answer."])
        together = _make_stream(["Paris is the capital of France."])
        with patch("app.main.classify_prompt", return_value="simple"), \
             patch("app.main._stream_haiku", haiku), \
             patch("app.main._stream_together", together), \
             patch("app.main.log_request"):
            resp = _post("What is the capital of France?")
        meta = _parse_frames(resp.text)[0]
        assert meta["escalated"] is True
        assert meta["model_used"] == "meta-llama/Llama-3.3-70B-Instruct-Turbo"

    def test_no_escalation_on_confident_response(self):
        with patch("app.main.classify_prompt", return_value="simple"), \
             patch("app.main._stream_haiku", _make_stream(["Paris is the capital of France."])), \
             patch("app.main.log_request"):
            resp = _post("What is the capital of France?")
        meta = _parse_frames(resp.text)[0]
        assert meta["escalated"] is False
        assert meta["model_used"] == "claude-haiku-4-5"

    def test_escalated_tokens_come_from_escalated_model(self):
        haiku = _make_stream(["I don't know."])
        together = _make_stream(["Escalated", " answer"])
        with patch("app.main.classify_prompt", return_value="simple"), \
             patch("app.main._stream_haiku", haiku), \
             patch("app.main._stream_together", together), \
             patch("app.main.log_request"):
            resp = _post("hard question")
        token_frames = [f for f in _parse_frames(resp.text) if f["type"] == "token"]
        texts = [f["text"] for f in token_frames]
        assert "Escalated" in texts

    def test_top_tier_does_not_escalate(self):
        with patch("app.main.classify_prompt", return_value="complex"), \
             patch("app.main._stream_openai", _make_stream(["I'm not sure."])), \
             patch("app.main.log_request"):
            resp = _post("hard question")
        meta = _parse_frames(resp.text)[0]
        assert meta["escalated"] is False
        assert meta["model_used"] == "gpt-4o"


# ── Error handling ─────────────────────────────────────────────────────────────

class TestStreamErrors:

    def test_error_frame_on_classifier_failure(self):
        with patch("app.main.classify_prompt", side_effect=Exception("classifier_down")):
            resp = _post("anything")
        frames = _parse_frames(resp.text)
        assert frames[0]["type"] == "error"
        assert "classifier_error" in frames[0]["message"]

    def test_error_frame_on_stream_failure(self):
        def _failing(*args, **kwargs):
            raise Exception("provider_down")
            yield  # pragma: no cover — makes this a generator function

        with patch("app.main.classify_prompt", return_value="simple"), \
             patch("app.main._stream_haiku", _failing):
            resp = _post("anything")
        frames = _parse_frames(resp.text)
        assert frames[0]["type"] == "error"

    def test_response_status_200_even_on_stream_error(self):
        """HTTP 200 is correct — errors are signalled in-stream, not via status."""
        def _failing(*args, **kwargs):
            raise Exception("provider_down")
            yield  # pragma: no cover

        with patch("app.main.classify_prompt", return_value="simple"), \
             patch("app.main._stream_haiku", _failing):
            resp = _post("anything")
        assert resp.status_code == 200
