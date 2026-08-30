"""Undergraduate audience filter and JD/interview library pagination."""

from fastapi.testclient import TestClient

from app import main as main_mod
from app.main import (
    is_graduate_targeted,
    is_xiaohongshu_sample,
    paginate_library,
    publish_library,
    sample_sort_date,
)


def _interview(sample_id: str, **fields) -> dict:
    row = {
        "id": sample_id,
        "company": sample_id,
        "role": "面经",
        "kind": "interview",
        "source_url": f"https://example.com/{sample_id}",
        "source_name": "牛客",
        "text": "问了 Attention",
    }
    row.update(fields)
    return row


def test_education_field_filters_master_and_phd() -> None:
    assert is_graduate_targeted({"education": "硕士"})
    assert is_graduate_targeted({"education": "博士"})
    assert is_graduate_targeted({"education": "Master"})
    assert not is_graduate_targeted({"education": "本科"})
    assert not is_graduate_targeted({"education": "本科或硕士"})


def test_text_filters_explicit_graduate_requirement() -> None:
    assert is_graduate_targeted({"text": "学历要求硕士及以上，熟悉 PyTorch。"})
    assert is_graduate_targeted({"requirements": "须为博士学历"})
    assert not is_graduate_targeted(
        {"text": "熟悉 Transformer 与大模型训练全流程，熟练使用 PyTorch。"}
    )


def test_publish_library_keeps_current_sourced_samples() -> None:
    payload = publish_library()
    assert payload["jds"]
    assert payload["interviews"]
    assert all(item.get("source_url") for item in payload["jds"])
    assert all(item.get("source_url") for item in payload["interviews"])


def test_api_jds_splits_kind_and_drops_graduate(monkeypatch) -> None:
    def fake_load(filename: str):
        if filename == "jds.json":
            return [
                {
                    "company": "硕博公司",
                    "role": "算法实习",
                    "kind": "jd",
                    "education": "硕士",
                    "source_url": "https://example.com/master",
                    "source_name": "招聘页",
                    "text": "做大模型",
                    "published_at": "2026-01-01",
                    "requirements": "Python",
                },
                {
                    "company": "本科公司",
                    "role": "LLM 实习",
                    "kind": "jd",
                    "education": "本科",
                    "source_url": "https://example.com/undergrad",
                    "source_name": "招聘页",
                    "text": "做大模型",
                    "published_at": "2026-02-01",
                    "requirements": "熟悉 Transformer",
                },
                {
                    "company": "混在 JD 里的面经",
                    "role": "一面",
                    "kind": "interview",
                    "source_url": "https://example.com/mix",
                    "source_name": "牛客",
                    "text": "问了 Attention",
                    "question_types": ["Attention"],
                    "experience": "项目拷打很深",
                },
            ]
        return [
            {
                "company": "文本硕博",
                "role": "面经",
                "kind": "interview",
                "source_url": "https://example.com/grad-text",
                "source_name": "牛客",
                "text": "学历要求硕士及以上才能进终面",
            }
        ]

    monkeypatch.setattr(main_mod, "_load_samples", fake_load)

    with TestClient(main_mod.app) as client:
        response = client.get("/api/jds")

    assert response.status_code == 200
    data = response.json()
    assert [item["company"] for item in data["jds"]] == ["本科公司"]
    assert [item["company"] for item in data["interviews"]] == ["混在 JD 里的面经"]
    assert data["jds"][0]["published_at"] == "2026-02-01"
    assert data["jds"][0]["requirements"] == "熟悉 Transformer"
    assert data["interviews"][0]["question_types"] == ["Attention"]
    assert data["interviews"][0]["experience"] == "项目拷打很深"


def test_sample_sort_date_uses_real_fields_and_skips_empty() -> None:
    assert sample_sort_date({"published_at": "2026-08-29"}) == "2026-08-29"
    assert (
        sample_sort_date({"published_at": "", "captured_at": "2026-08-30"})
        == "2026-08-30"
    )
    assert sample_sort_date({"created_at": "2026/07/13"}) == "2026-07-13"
    assert (
        sample_sort_date({"published_at": "  ", "date": "2026-01-02T18:00:00"})
        == "2026-01-02"
    )
    assert sample_sort_date({"company": "无日期"}) == ""


def test_publish_library_sorts_newest_first_not_xiaohongshu(monkeypatch) -> None:
    def fake_load(filename: str):
        if filename == "jds.json":
            return []
        return [
            _interview(
                "xhs-old",
                source_url="https://www.xiaohongshu.com/explore/old",
                source_name="小红书",
                published_at="2026-01-01",
            ),
            _interview(
                "nowcoder-new",
                source_url="https://www.nowcoder.com/feed/new",
                source_name="牛客网",
                published_at="2026-08-20",
            ),
            _interview("undated", published_at="", captured_at=""),
            _interview("mid", published_at="2026-03-15"),
        ]

    monkeypatch.setattr(main_mod, "_load_samples", fake_load)
    payload = publish_library()
    assert [item["id"] for item in payload["interviews"]] == [
        "nowcoder-new",
        "mid",
        "xhs-old",
        "undated",
    ]
    assert payload["interviews"][0]["sort_date"] == "2026-08-20"
    assert "sort_date" not in payload["interviews"][-1]
    assert not is_xiaohongshu_sample(payload["interviews"][0])


def test_paginate_library_page_one_last_and_empty(monkeypatch) -> None:
    def fake_load(filename: str):
        if filename == "jds.json":
            return []
        return [
            _interview(f"iv-{index:02d}", published_at=f"2026-08-{index:02d}")
            for index in range(1, 21)
        ]

    monkeypatch.setattr(main_mod, "_load_samples", fake_load)

    first = paginate_library("interview", page=1, page_size=9)
    assert first["total"] == 20
    assert first["page"] == 1
    assert first["pages"] == 3
    assert first["page_size"] == 9
    assert first["type"] == "interview"
    assert [item["id"] for item in first["items"]] == [
        f"iv-{index:02d}" for index in range(20, 11, -1)
    ]
    assert first["items"][0]["sort_date"] == "2026-08-20"

    last = paginate_library("interview", page=3, page_size=9)
    assert last["page"] == 3
    assert [item["id"] for item in last["items"]] == ["iv-02", "iv-01"]
    assert last["items"][-1]["sort_date"] == "2026-08-01"

    empty = paginate_library("interview", page=4, page_size=9)
    assert empty["items"] == []
    assert empty["total"] == 20
    assert empty["page"] == 4
    assert empty["pages"] == 3


def test_paginate_library_empty_collection(monkeypatch) -> None:
    monkeypatch.setattr(main_mod, "_load_samples", lambda filename: [])
    payload = paginate_library("interview", page=1, page_size=9)
    assert payload["items"] == []
    assert payload["total"] == 0
    assert payload["page"] == 1
    assert payload["pages"] == 0


def test_api_jds_paginated_interview_contract(monkeypatch) -> None:
    def fake_load(filename: str):
        if filename == "jds.json":
            return []
        return [
            _interview("old", published_at="2026-01-01"),
            _interview("new", published_at="2026-08-29"),
        ]

    monkeypatch.setattr(main_mod, "_load_samples", fake_load)

    with TestClient(main_mod.app) as client:
        response = client.get(
            "/api/jds",
            params={"type": "interview", "page": 1, "page_size": 9},
        )
        bad = client.get("/api/jds", params={"type": "unknown"})

    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["pages"] == 1
    assert data["total"] == 2
    assert [item["id"] for item in data["items"]] == ["new", "old"]
    assert bad.status_code == 400
