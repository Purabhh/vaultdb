import json

import httpx
import numpy as np
import pytest

from vaultdb.embedder import Embedder, EmbedderError


def _ok(dim: int = 768):
    seen: list[list[str]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        assert req.url.path == "/api/embed" and body["model"] == "nomic-embed-text"
        seen.append(body["input"])
        return httpx.Response(200, json={"embeddings": [[3.0, 4.0] + [0.0] * (dim - 2) for _ in body["input"]]})

    return seen, httpx.MockTransport(handler)


def test_prefixes_and_batching() -> None:
    seen, transport = _ok()
    e = Embedder(batch_size=2, transport=transport)
    out = e.embed_documents(["a", "b", "c"])
    assert out.shape == (3, 768) and out.dtype == np.float32
    assert seen[0] == ["search_document: a", "search_document: b"] and len(seen) == 2
    q = e.embed_query("q")
    assert seen[-1] == ["search_query: q"] and q.shape == (768,)


def test_vectors_are_normalised() -> None:
    _, transport = _ok()
    v = Embedder(transport=transport).embed_query("q")
    assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-6 and abs(v[0] - 0.6) < 1e-6


def test_no_prefixes_when_disabled() -> None:
    seen, transport = _ok()
    Embedder(use_prefixes=False, transport=transport).embed_documents(["a"])
    assert seen == [["a"]]


def test_empty_input_makes_no_request() -> None:
    seen, transport = _ok()
    assert Embedder(transport=transport).embed_documents([]).shape == (0, 768)
    assert seen == []


def test_connection_refused_message() -> None:
    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(EmbedderError, match="Ollama is not running"):
        Embedder(transport=httpx.MockTransport(boom)).embed_query("q")


def test_model_not_pulled_message() -> None:
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": 'model "nomic-embed-text" not found, try pulling it first'})

    with pytest.raises(EmbedderError, match="ollama pull nomic-embed-text"):
        Embedder(transport=httpx.MockTransport(h)).embed_query("q")


def test_other_http_error_is_reported() -> None:
    h = lambda req: httpx.Response(500, text="boom")  # noqa: E731
    with pytest.raises(EmbedderError, match="500"):
        Embedder(transport=httpx.MockTransport(h)).embed_query("q")


def test_wrong_dimension_rejected() -> None:
    _, transport = _ok(dim=512)
    with pytest.raises(EmbedderError, match="768"):
        Embedder(transport=transport).embed_query("q")


@pytest.mark.ollama
def test_real_ollama_roundtrip() -> None:
    v = Embedder().embed_query("glass button")
    assert v.shape == (768,) and abs(float(np.linalg.norm(v)) - 1) < 1e-4


def test_context_length_rejection_is_an_input_error() -> None:
    from vaultdb.embedder import EmbedderInputError
    h = lambda req: httpx.Response(400, json={"error": "the input length exceeds the context length"})  # noqa: E731
    with pytest.raises(EmbedderInputError):
        Embedder(transport=httpx.MockTransport(h)).embed_query("q")


def test_unavailable_errors_are_not_input_errors() -> None:
    from vaultdb.embedder import EmbedderInputError

    def boom(req):
        raise httpx.ConnectError("refused")
    with pytest.raises(EmbedderError) as e:
        Embedder(transport=httpx.MockTransport(boom)).embed_query("q")
    assert not isinstance(e.value, EmbedderInputError)


def test_old_ollama_404_is_not_reported_as_missing_model() -> None:
    h = lambda req: httpx.Response(404, text="404 page not found")  # noqa: E731
    with pytest.raises(EmbedderError) as e:
        Embedder(transport=httpx.MockTransport(h)).embed_query("q")
    assert "ollama pull" not in str(e.value)


def test_base_url_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("VAULTDB_OLLAMA_URL", "http://example.invalid:9999")
    assert Embedder().base_url == "http://example.invalid:9999"
