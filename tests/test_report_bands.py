"""Report primary-band contract: excellent and weak sessions must differ."""

from app.report import (
    HIGH_PRIMARY_BANDS,
    LOW_PRIMARY_BANDS,
    PRIMARY_BAND_RANK,
    compose_report_text,
    extract_primary_band,
    load_report_prompt,
)
from tests.test_report_snapshot import _sample_report


def _report_with_band(band: str) -> str:
    return compose_report_text(
        f"## 总评\n\n整场主档：{band}\n依据来自本场原句。\n\n"
        "## 岗位本质对照\n\n对照岗位本质。\n\n"
        "## 知识建议\n\n用项目对象补缺口。\n\n"
        "## 项目改良\n\n几小时内做最小改造。"
    )


def test_extract_primary_band_from_sample_report() -> None:
    assert extract_primary_band(_sample_report()) == "懂但讲不出"


def test_excellent_and_weak_bands_are_different_ranks() -> None:
    excellent = extract_primary_band(_report_with_band("真懂"))
    weak = extract_primary_band(_report_with_band("真不懂"))
    assert excellent in HIGH_PRIMARY_BANDS
    assert weak in LOW_PRIMARY_BANDS
    assert PRIMARY_BAND_RANK[excellent] > PRIMARY_BAND_RANK[weak]


def test_report_prompt_requires_calibration() -> None:
    prompt = load_report_prompt()
    assert "整场主档：" in prompt
    assert "真懂" in prompt
    assert "真不懂" in prompt
    assert "禁止默认「懂但讲不出」" in prompt
    assert "naive" in prompt or "toy" in prompt
    assert "升格" in prompt
    assert "rerank" in prompt
    assert "万卡" in prompt
