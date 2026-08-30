"""Undergraduate audience filter for /api/jds."""

from fastapi.testclient import TestClient

from app import main as main_mod
from app.main import is_graduate_targeted, publish_library


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
