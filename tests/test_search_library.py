"""Lexical search over collected JD/interview originals."""

from app.tools.search_library import search_library


def test_search_hits_real_attention_question() -> None:
    result = search_library("Decoder 因果注意力 QKV", kind="interview")
    assert result.ok
    assert result.hits
    blob = " ".join(hit.snippet for hit in result.hits)
    assert "QKV" in blob or "注意力" in blob or "Attention" in blob or "attention" in blob.lower()
    assert all(hit.snippet for hit in result.hits)
    assert all(hit.source_url for hit in result.hits)


def test_search_prefers_lora_over_unrelated_when_query_is_lora() -> None:
    result = search_library("LoRA 秩 初始化", kind="interview")
    assert result.ok
    assert result.hits
    top = result.hits[0].snippet.lower()
    assert "lora" in top or "秩" in result.hits[0].snippet


def test_empty_query_fails_cleanly() -> None:
    result = search_library("   ")
    assert not result.ok
    assert "空" in result.error


def test_public_hint_has_no_raw_dump() -> None:
    result = search_library("KV cache", kind="interview")
    public = result.for_public()
    assert "检索面经" in public
    assert "http" not in public
