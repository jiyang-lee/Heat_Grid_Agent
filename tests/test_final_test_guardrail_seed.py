from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_final_test_chat_seeds_at_least_ten_distinct_guardrails() -> None:
    sql = (ROOT / "migrations" / "023_final_test_demo_packages.sql").read_text(encoding="utf-8")
    categories = re.findall(r"'category',\s*'([^']+)'", sql)

    assert len(categories) >= 10
    assert len(categories) == len(set(categories))
    assert {
        "jailbreak",
        "prompt_leak",
        "profanity",
        "recipe_replacement",
        "off_topic",
        "safety_bypass",
        "approval_bypass",
        "unsafe_action",
        "credential_request",
        "code_injection",
    }.issubset(categories)


def test_final_test_chat_guardrails_are_evaluated_before_domain_responses() -> None:
    source = (
        ROOT
        / "frontend"
        / "src"
        / "final-test"
        / "FinalTestProjectChat.tsx"
    ).read_text(encoding="utf-8")

    guardrail_lookup = source.index("matchesRule(message, script.guardrails)")
    domain_lookup = source.index("matchesRule(message, script.responses)")
    assert guardrail_lookup < domain_lookup


def test_final_test_version_seed_contains_three_prebuilt_versions_and_required_greeting() -> None:
    sql = (ROOT / "migrations" / "024_final_test_document_versions.sql").read_text(encoding="utf-8")

    assert "work_order_versions" in sql
    assert "report_versions" in sql
    assert "'version', 1" in sql
    assert "'version', 2" in sql
    assert "'version', 3" in sql
    assert "안녕하세요. 이 대화는 " in sql
    assert "번 기계실 관련 대화만 답변합니다." in sql
    assert "작업목적의 내용을 세부적으로 바꿔줘" in sql
    assert "preview_document_version" in sql
    assert "confirmation_message" in sql
