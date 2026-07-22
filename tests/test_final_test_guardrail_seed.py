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
