from codeimpact.diff_parser import parse_git_diff
from codeimpact.risk import _build_risk_prompt, fallback_risk_assessment


def test_fallback_risk_assessment_has_llm_shape() -> None:
    parsed = parse_git_diff(_diff_for("pkg/core.py"))

    assessment = fallback_risk_assessment(parsed, [])

    assert assessment["risk_level"] == "low"
    assert assessment["risk_source"] == "fallback"
    assert assessment["test_focus"]
    assert assessment["review_focus"]
    assert 0 < assessment["confidence"] <= 1
    assert assessment["assumptions"]
    assert assessment["evidence"][0]["path"] == "pkg/core.py"
    assert "return 2" in assessment["evidence"][0]["added"]


def test_risk_prompt_contains_rubric_and_diff_evidence() -> None:
    parsed = parse_git_diff(_diff_for("pkg/core.py"))

    prompt = _build_risk_prompt("repo", parsed, [], retrieved_context=[{"path": "tests/test_core.py", "snippet": "run"}])

    assert "Risk rubric" in prompt
    assert "diff_hunk_evidence" in prompt
    assert '"test_focus"' in prompt
    assert '"review_focus"' in prompt
    assert '"confidence"' in prompt
    assert "retrieved_context" in prompt
    assert "tests/test_core.py" in prompt
    assert "return 2" in prompt


def _diff_for(path: str) -> str:
    return "\n".join(
        [
            f"diff --git a/{path} b/{path}",
            f"--- a/{path}",
            f"+++ b/{path}",
            "@@ -1,2 +1,2 @@",
            " def service():",
            "-    return 1",
            "+    return 2",
        ]
    )
