"""JSON thought field can be read while the object is still streaming."""

from app.llm import partial_json_string_field


def test_partial_json_string_field_streams_incomplete_thought() -> None:
    buffer = '{"thought": "评价：答得虚\\n查代码：否'
    thought = partial_json_string_field(buffer, "thought")
    assert thought is not None
    assert thought.startswith("评价：答得虚")
    assert "查代码：否" in thought


def test_partial_json_string_field_unescapes_newlines() -> None:
    buffer = '{"thought": "评价：好。\\n查代码：否\\n本方向结束：否", "direction_done": false}'
    thought = partial_json_string_field(buffer, "thought")
    assert thought == "评价：好。\n查代码：否\n本方向结束：否"
