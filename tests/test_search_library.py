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
    assert "检索到" in public
    assert "相关面经" in public
    assert "http" not in public
    assert "项目总览" not in public
    hits = result.public_hits()
    assert hits
    assert hits[0]["snippet"]
    assert hits[0]["id"]


def test_topic_query_uses_last_question_not_process_talk() -> None:
    from app.tools.search_library import topic_search_query

    query = topic_search_query(
        direction_title="项目总览",
        last_question="RoPE 具体旋转的是哪一部分？",
        answer="请继续问吧",
    )
    assert "RoPE" in query
    assert "继续问" not in query


def test_search_hit_count_caps_at_five() -> None:
    from app.tools.search_library import MAX_HITS

    assert MAX_HITS == 5
    rope = search_library("RoPE 外推", kind="interview")
    kv = search_library("KV cache", kind="interview")
    assert 0 <= len(rope.hits) <= 5
    assert 0 <= len(kv.hits) <= 5
    weak = search_library("token ID hidden state", kind="interview")
    assert weak.ok
    assert len(weak.hits) <= 5


def test_process_talk_does_not_return_padded_hits() -> None:
    from app.tools.search_library import is_unsearchable_query

    assert is_unsearchable_query("请继续问吧")
    assert is_unsearchable_query("换个话题吧")
    assert not is_unsearchable_query("RoPE 外推怎么做")
    for query in ("请继续问吧", "换个话题吧", "好的"):
        result = search_library(query, kind="interview")
        assert result.ok
        assert result.hits == []
        assert "没有检索到" in result.for_public()


def test_find_library_sample_returns_full_note() -> None:
    from app.main import find_library_sample

    sample = find_library_sample("bytedance-llm-algorithm-intern-interview")
    assert sample is not None
    assert sample["id"] == "bytedance-llm-algorithm-intern-interview"
    assert sample.get("text")
